"""Self-healing review loop with model escalation.

Both ``code_reviewer`` and ``visual_reviewer`` are driven by the exact same
``ReviewLoop`` class.  The *only* difference is the ``ReviewConfig`` passed in,
which selects the manim render flags and the system prompts used for
review / fix requests.

Model escalation: gemma-4-31b-it (1 attempt) → gemini-3-flash-preview (1 attempt)
→ gemini-3.5-flash (N attempts, default 2).
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from typing import Any

from shared.schemas.hitl import ReviewIterationRecord, ReviewLoopResult

from app.llm import GoogleLLM
from app.models import ModelTier, load_review_loop_tiers
from app.prompts import (
    CODE_FIX_PROMPT,
    CODE_REVIEW_PROMPT,
    VISUAL_FIX_PROMPT,
    VISUAL_REVIEW_PROMPT,
)
from app.renderer import ManimError, parse_manim_errors, render_manim_for_validation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config: makes code_reviewer and visual_reviewer identical except prompts/flags
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReviewConfig:
    """Only thing that distinguishes code_reviewer from visual_reviewer."""
    review_prompt: str      # system prompt to analyse errors / visual issues
    fix_prompt: str         # system prompt to produce the fix
    render_flags: list[str] # extra manim flags (e.g. ["-s"] for save-last-frame)
    uses_vision: bool       # True → sends frame image to VLM


CODE_REVIEW_CONFIG = ReviewConfig(
    review_prompt=CODE_REVIEW_PROMPT,
    fix_prompt=CODE_FIX_PROMPT,
    render_flags=[],            # no -s; we only need stderr
    uses_vision=False,
)

VISUAL_REVIEW_CONFIG = ReviewConfig(
    review_prompt=VISUAL_REVIEW_PROMPT,
    fix_prompt=VISUAL_FIX_PROMPT,
    render_flags=["-s"],        # save last frame, skip video
    uses_vision=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class CodeFix:
    can_fix: bool
    original_code: str
    replacement_code: str
    explanation: str


def apply_partial_fix(code: str, original: str, replacement: str) -> str:
    """Apply a minimal fix by replacing the first occurrence of *original*."""
    if not original or original not in code:
        return code
    return code.replace(original, replacement, 1)


def is_same_error(a: ManimError | dict, b: ManimError | dict) -> bool:
    """Two errors are considered 'the same' if line AND message both match."""
    a_line = a.line if isinstance(a, ManimError) else a.get("line")
    b_line = b.line if isinstance(b, ManimError) else b.get("line")
    a_msg = (a.message if isinstance(a, ManimError) else a.get("message", "")).strip()
    b_msg = (b.message if isinstance(b, ManimError) else b.get("message", "")).strip()
    if a_line is not None and b_line is not None:
        return a_line == b_line and a_msg == b_msg
    return a_msg == b_msg


def _parse_json(text: str) -> dict[str, Any]:
    """Best-effort JSON extraction from LLM output."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return dict(json.loads(text))
    except (json.JSONDecodeError, TypeError, ValueError):
        # Try to find a JSON object in the text
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return dict(json.loads(text[start : end + 1]))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
    return {}


# ---------------------------------------------------------------------------
# ReviewLoop – the engine
# ---------------------------------------------------------------------------

class ReviewLoop:
    """Unified self-healing review loop for code_reviewer and visual_reviewer.

    Both agents use this exact same class; only ``config`` differs.
    """

    def __init__(
        self,
        llm: GoogleLLM,
        tiers: list[ModelTier] | None = None,
    ) -> None:
        self.llm = llm
        self.tiers = tiers or load_review_loop_tiers()

    # -- public API ---------------------------------------------------------

    def run(
        self,
        code: str,
        config: ReviewConfig,
        context: dict[str, Any] | None = None,
    ) -> ReviewLoopResult:
        """Execute the review loop with model escalation.

        Returns a ``ReviewLoopResult`` with the (possibly fixed) code and
        full iteration history.
        """
        iterations: list[ReviewIterationRecord] = []
        total_attempts = 0

        for tier in self.tiers:
            prev_errors: list[ManimError | dict] | None = None

            for _attempt in range(tier.max_attempts):
                total_attempts += 1

                # 1. Validate (run manim / VLM frame analysis)
                try:
                    errors, frame_bytes = self._validate(code, config, tier.model)
                except Exception as exc:
                    logger.warning("Validation failed with LLM error on model %s: %s", tier.model, exc)
                    record = ReviewIterationRecord(
                        iteration=len(iterations) + 1,
                        model=tier.model,
                        error_summary=f"Validation LLM error: {exc}",
                        escalated=True,
                    )
                    iterations.append(record)
                    break  # escalate to next model

                if not errors:
                    return ReviewLoopResult(
                        passed=True,
                        manim_code=code,
                        iterations=iterations,
                        total_attempts=total_attempts,
                    )

                record = ReviewIterationRecord(
                    iteration=len(iterations) + 1,
                    model=tier.model,
                    error_summary=self._error_summary(errors),
                )

                # 2. Try to fix
                try:
                    fix = self._request_fix(
                        code, errors, config, tier.model, frame_bytes,
                    )
                except Exception as exc:
                    logger.warning("Fix request failed with LLM error on model %s: %s", tier.model, exc)
                    record.escalated = True
                    record.error_summary = f"{record.error_summary or ''}; LLM error: {exc}".strip("; ")
                    iterations.append(record)
                    break  # escalate to next model

                if fix is None or not fix.can_fix:
                    record.escalated = True
                    iterations.append(record)
                    logger.info(
                        "Model %s cannot fix → escalating (attempt %d)",
                        tier.model, total_attempts,
                    )
                    break  # escalate to next model

                # 3. Apply fix
                prev_code = code
                code = apply_partial_fix(code, fix.original_code, fix.replacement_code)
                record.fix_applied = fix.explanation

                # 4. Re-validate
                try:
                    new_errors, _ = self._validate(code, config, tier.model)
                except Exception as exc:
                    logger.warning("Re-validation failed with LLM error on model %s: %s", tier.model, exc)
                    record.escalated = True
                    iterations.append(record)
                    break  # escalate to next model

                if not new_errors:
                    iterations.append(record)
                    return ReviewLoopResult(
                        passed=True,
                        manim_code=code,
                        iterations=iterations,
                        total_attempts=total_attempts,
                    )

                # Same error at same line? → escalate
                if errors and new_errors and is_same_error(errors[0], new_errors[0]):
                    record.same_error = True
                    record.escalated = True
                    code = prev_code  # revert unsuccessful fix
                    iterations.append(record)
                    logger.info(
                        "Same error persists after fix by %s → escalating",
                        tier.model,
                    )
                    break  # escalate

                # Different error → continue with same model
                iterations.append(record)
                prev_errors = new_errors  # noqa: F841

        # All tiers exhausted
        final_err = self._error_summary(errors) if errors else None  # type: ignore[possibly-undefined]
        return ReviewLoopResult(
            passed=False,
            manim_code=code,
            iterations=iterations,
            total_attempts=total_attempts,
            final_error=final_err,
        )

    # -- private: validation ------------------------------------------------

    def _validate(
        self,
        code: str,
        config: ReviewConfig,
        model: str,
    ) -> tuple[list[ManimError | dict], bytes | None]:
        """Validate code by running manim.

        For code review: parse stderr errors.
        For visual review: render with -s and send frame to VLM.
        """
        from app.renderer import UnsafeManimCode

        try:
            render = render_manim_for_validation(code, extra_flags=config.render_flags)
        except UnsafeManimCode as exc:
            import re
            msg = str(exc)
            m = re.search(r"line (\d+)", msg)
            line = int(m.group(1)) if m else None
            return [ManimError(line=line, message=msg)], None

        frame_bytes: bytes | None = None
        temp_dir = render.temp_dir

        try:
            if not render.success:
                # Manim crashed → code errors (both modes)
                errors = parse_manim_errors(render.stderr)
                return errors or [ManimError(line=None, message=render.stderr[-500:])], None

            if not config.uses_vision:
                # Code review: no errors if manim succeeded
                return [], None

            # Visual review: read the saved frame and ask VLM
            if render.image_path and render.image_path.is_file():
                frame_bytes = render.image_path.read_bytes()
            else:
                return [ManimError(line=None, message="Manim succeeded but no frame was saved")], None

            issues = self._vlm_analyse_frame(frame_bytes, code, config, model)
            return issues, frame_bytes

        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _vlm_analyse_frame(
        self,
        frame_bytes: bytes,
        code: str,
        config: ReviewConfig,
        model: str,
    ) -> list[dict]:
        """Send the rendered frame to a VLM for visual quality analysis."""
        user_msg = f"Source code:\n```python\n{code}\n```\n\nAnalyse the rendered frame above."
        raw = self.llm.complete_with_image(
            messages=[
                {"role": "system", "content": config.review_prompt},
                {"role": "user", "content": user_msg},
            ],
            image_bytes=frame_bytes,
            model=model,
            temperature=0.1,
            max_tokens=4096,
        )
        parsed = _parse_json(raw)
        if not parsed.get("has_issues"):
            return []
        issues = parsed.get("issues", [])
        return [issue for issue in issues if isinstance(issue, dict)]

    # -- private: fix -------------------------------------------------------

    def _request_fix(
        self,
        code: str,
        errors: list[ManimError | dict],
        config: ReviewConfig,
        model: str,
        frame_bytes: bytes | None,
    ) -> CodeFix | None:
        """Ask an LLM to produce a partial code fix."""
        error_text = "\n".join(
            f"  Line {e.line if isinstance(e, ManimError) else e.get('line', '?')}: "
            f"{e.message if isinstance(e, ManimError) else e.get('message', e.get('description', str(e)))}"
            for e in errors
        )
        user_msg = (
            f"Source code:\n```python\n{code}\n```\n\n"
            f"Errors / issues found:\n{error_text}\n\n"
            "Provide the minimal fix."
        )

        if config.uses_vision and frame_bytes:
            raw = self.llm.complete_with_image(
                messages=[
                    {"role": "system", "content": config.fix_prompt},
                    {"role": "user", "content": user_msg},
                ],
                image_bytes=frame_bytes,
                model=model,
                temperature=0.1,
                max_tokens=4096,
            )
        else:
            raw = self.llm.complete(
                messages=[
                    {"role": "system", "content": config.fix_prompt},
                    {"role": "user", "content": user_msg},
                ],
                model=model,
                temperature=0.1,
                max_tokens=4096,
            )

        parsed = _parse_json(raw)
        if not parsed:
            return None
        return CodeFix(
            can_fix=bool(parsed.get("can_fix", False)),
            original_code=str(parsed.get("original_code", "")),
            replacement_code=str(parsed.get("replacement_code", "")),
            explanation=str(parsed.get("explanation", "")),
        )

    # -- private: helpers ---------------------------------------------------

    @staticmethod
    def _error_summary(errors: list[ManimError | dict]) -> str:
        parts: list[str] = []
        for e in errors[:3]:
            if isinstance(e, ManimError):
                parts.append(f"L{e.line}: {e.message}" if e.line else e.message)
            elif isinstance(e, dict):
                parts.append(str(e.get("message") or e.get("description") or str(e)))
        return "; ".join(parts)[:500]
