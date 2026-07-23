"""Self-healing review loop with model escalation.

Both ``code_reviewer`` and ``visual_reviewer`` are driven by the exact same
``ReviewLoop`` class.  The *only* difference is the ``ReviewConfig`` passed in,
which selects the manim render flags and the system prompts used for
review / fix requests.

Model escalation: gemma-4-31b-it (1 attempt) → gemini-3-flash-preview (1 attempt)
→ gemini-3.5-flash (N attempts, default 3).
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import io
import json
import logging
import re
import shutil
import textwrap
import tokenize
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from shared.schemas.hitl import ReviewIterationRecord, ReviewLoopResult

from app.llm import GoogleLLM
from app.models import AgentModel, ModelTier, load_review_loop_tiers
from app.prompts import (
    CODE_FIX_PROMPT,
    CODE_REVIEW_PROMPT,
    VISUAL_FIX_PROMPT,
    VISUAL_REVIEW_PROMPT,
)
from app.renderer import ManimError, parse_manim_errors, render_manim_for_validation
from app.runtime_api_context import build_runtime_api_context, format_runtime_api_context

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config: makes code_reviewer and visual_reviewer identical except prompts/flags
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewConfig:
    """Only thing that distinguishes code_reviewer from visual_reviewer."""

    review_prompt: str  # system prompt to analyse errors / visual issues
    fix_prompt: str  # system prompt to produce the fix
    render_flags: list[str]  # extra manim flags (e.g. ["-s"] for save-last-frame)
    uses_vision: bool  # True → sends frame image to VLM


CODE_REVIEW_CONFIG = ReviewConfig(
    review_prompt=CODE_REVIEW_PROMPT,
    fix_prompt=CODE_FIX_PROMPT,
    render_flags=[],  # no -s; we only need stderr
    uses_vision=False,
)

VISUAL_REVIEW_CONFIG = ReviewConfig(
    review_prompt=VISUAL_REVIEW_PROMPT,
    fix_prompt=VISUAL_FIX_PROMPT,
    render_flags=["-s"],  # save last frame, skip video
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


@dataclass(frozen=True)
class RepairAttempt:
    """One failed strategy for the currently unresolved error only."""

    error_fingerprint: str
    model: str
    outcome: str
    original_code: str = ""
    replacement_code: str = ""
    explanation: str = ""
    strategy_fingerprint: str | None = None


@dataclass
class PendingPatchCheckpoint:
    """A locally applied patch awaiting a conclusive validation result."""

    previous_code: str
    candidate_code: str
    previous_errors: list[ManimError | dict]
    error_fingerprint: str
    record: ReviewIterationRecord


@dataclass(frozen=True)
class ErrorEpisode:
    """One validated error bound to the exact source revision that produced it."""

    number: int
    source_revision: str
    error_fingerprint: str
    errors: tuple[ManimError | dict, ...]
    frame_bytes: bytes | None = None


def source_revision(code: str) -> str:
    """Short content identity used to prevent stale error/source pairings."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]


def error_fingerprint(errors: list[ManimError | dict], code: str = "") -> str:
    """Stable identity for one concrete failure site in the current source."""
    if not errors:
        return ""
    primary = errors[0]
    line = primary.line if isinstance(primary, ManimError) else primary.get("line")
    message = (
        primary.message
        if isinstance(primary, ManimError)
        else str(primary.get("message") or primary.get("description") or primary)
    )
    normalised = re.sub(r"/[^\s:]+/scene\.py", "scene.py", message.lower())
    normalised = re.sub(r"\s+", " ", normalised).strip()
    location = _source_location(code, line)
    payload = f"{normalised}|line={line}|location={location}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _source_location(code: str, line: object) -> str:
    if not isinstance(line, int) or isinstance(line, bool):
        return "unknown"
    lines = code.splitlines()
    source = lines[line - 1].strip() if 1 <= line <= len(lines) else ""
    scopes: list[tuple[int, str]] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.lineno <= line <= getattr(node, "end_lineno", node.lineno):
                scopes.append((node.lineno, node.name))
    scope = ".".join(name for _, name in sorted(scopes))
    return f"{scope}:{source[:300]}"


def semantic_strategy_fingerprint(original: str, replacement: str) -> str:
    """Fingerprint the transformation, ignoring wrappers and formatting.

    A rename such as ``ShowCreation`` to ``Create`` is the same repair strategy
    even when a later model selects a larger/different surrounding excerpt.
    """
    before = _semantic_tokens(original)
    after = _semantic_tokens(replacement)
    matcher = difflib.SequenceMatcher(a=before, b=after, autojunk=False)
    changes = [
        {"before": before[i1:i2], "after": after[j1:j2]}
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    ]
    payload = json.dumps(changes, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    if not changes:
        payload = f"{_semantic_code(original)}=>{_semantic_code(replacement)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _semantic_tokens(source: str) -> list[str]:
    candidate = textwrap.dedent(source).strip()
    ignored = {
        tokenize.ENCODING,
        tokenize.ENDMARKER,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.NEWLINE,
        tokenize.NL,
    }
    try:
        return [
            f"{token.type}:{token.string}"
            for token in tokenize.generate_tokens(io.StringIO(candidate).readline)
            if token.type not in ignored
        ]
    except (IndentationError, tokenize.TokenError):
        return [re.sub(r"\s+", "", candidate)]


def _semantic_code(source: str) -> str:
    candidate = textwrap.dedent(source).strip()
    try:
        return ast.dump(ast.parse(candidate), annotate_fields=True, include_attributes=False)
    except SyntaxError:
        # Partial expressions and intentionally broken snippets may not parse.
        # A token-light fallback still treats formatting-only changes as equal.
        return re.sub(r"\s+", "", candidate)


def validate_partial_fix(code: str, original: str, replacement: str) -> str | None:
    """Return a rejection reason unless a reviewer supplied a safe, small patch.

    Reviewers receive the full file as context, but may only alter one unique
    consecutive source excerpt.  This prevents a malformed response or an
    enthusiastic reviewer from replacing the entire scene with a rewrite.
    """
    if not original:
        return "Reviewer did not provide the exact source excerpt to replace"
    if original == replacement:
        return "Reviewer replacement does not change the source"
    occurrences = code.count(original)
    if occurrences != 1:
        return (
            "Reviewer source excerpt must occur exactly once "
            f"(found {occurrences} occurrences)"
        )
    if original.strip() == code.strip():
        return "Reviewer attempted to replace the entire source file"

    source_lines = max(1, len(code.splitlines()))
    patch_lines = max(len(original.splitlines()), len(replacement.splitlines()))
    # A patch is deliberately capped both absolutely and relative to the file.
    # Small scenes still have room for a short, coherent local replacement.
    max_patch_lines = min(12, max(1, (source_lines + 4) // 5))
    if patch_lines > max_patch_lines:
        return (
            f"Reviewer proposed {patch_lines} changed lines; "
            f"local fixes are limited to {max_patch_lines} lines"
        )
    return None


def apply_partial_fix(code: str, original: str, replacement: str) -> str:
    """Apply a minimal fix by replacing the first occurrence of *original*."""
    if validate_partial_fix(code, original, replacement) is not None:
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


def _same_failure_site_after_patch(
    previous_errors: list[ManimError | dict],
    new_errors: list[ManimError | dict],
    previous_code: str,
    patched_code: str,
) -> bool:
    """Distinguish line drift from execution advancing to another occurrence.

    The patch may insert/delete lines, so raw line equality is insufficient.
    Equal diff blocks map the new traceback line back to the old source. A new
    error inside the changed block is conservatively treated as a failed repair;
    a different unchanged source location means execution advanced.
    """
    if not previous_errors or not new_errors:
        return False
    previous = previous_errors[0]
    current = new_errors[0]
    previous_message = (
        previous.message if isinstance(previous, ManimError) else previous.get("message", "")
    ).strip()
    current_message = (
        current.message if isinstance(current, ManimError) else current.get("message", "")
    ).strip()
    if previous_message != current_message:
        return False

    previous_line = previous.line if isinstance(previous, ManimError) else previous.get("line")
    current_line = current.line if isinstance(current, ManimError) else current.get("line")
    if not isinstance(previous_line, int) or not isinstance(current_line, int):
        return True

    old_lines = previous_code.splitlines()
    new_lines = patched_code.splitlines()
    current_index = current_line - 1
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    for tag, old_start, _old_end, new_start, new_end in matcher.get_opcodes():
        if not (new_start <= current_index < new_end):
            continue
        if tag == "equal":
            mapped_line = old_start + (current_index - new_start) + 1
            return mapped_line == previous_line
        return True
    return True


def _parse_json(text: str) -> dict[str, Any]:
    """Extract one object from strict JSON or common model wrappers.

    Markdown fences and surrounding prose are presentation noise, not a reason
    to discard an otherwise valid repair. Parsing remains data-only: no code is
    evaluated, and downstream schema checks still require exact typed fields.
    """
    objects = _parse_json_objects(text)
    return objects[0] if objects else {}


def _parse_json_objects(text: str) -> list[dict[str, Any]]:
    """Return parseable object candidates in presentation order."""
    candidates: list[str] = [text.strip()]
    candidates.extend(
        match.group(1).strip()
        for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    )
    candidates.extend(_balanced_json_objects(text))

    seen: set[str] = set()
    objects: list[dict[str, Any]] = []
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        escaped_controls = _escape_json_string_controls(candidate)
        variants = [
            candidate,
            escaped_controls,
            _remove_json_trailing_commas(candidate),
            _remove_json_trailing_commas(escaped_controls),
        ]
        for variant in variants:
            try:
                parsed = json.loads(variant)
            except (json.JSONDecodeError, TypeError, ValueError):
                parsed = None
            if isinstance(parsed, dict):
                objects.append(parsed)
                break
        else:
            # Some models return a Python-style literal despite an explicit
            # JSON instruction. ``literal_eval`` accepts only inert data.
            try:
                literal = ast.literal_eval(candidate)
            except (SyntaxError, ValueError):
                literal = None
            if isinstance(literal, dict):
                objects.append(literal)
    return objects


def _escape_json_string_controls(text: str) -> str:
    """Escape raw control characters only when they occur inside JSON strings."""
    output: list[str] = []
    in_string = False
    escaped = False
    for char in text:
        if not in_string:
            output.append(char)
            if char == '"':
                in_string = True
            continue
        if escaped:
            output.append(char)
            escaped = False
        elif char == "\\":
            output.append(char)
            escaped = True
        elif char == '"':
            output.append(char)
            in_string = False
        elif char == "\n":
            output.append("\\n")
        elif char == "\r":
            output.append("\\r")
        elif char == "\t":
            output.append("\\t")
        elif ord(char) < 0x20:
            output.append(f"\\u{ord(char):04x}")
        else:
            output.append(char)
    return "".join(output)


def _remove_json_trailing_commas(text: str) -> str:
    """Remove commas before a closing object/array without touching code strings."""
    output: list[str] = []
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            output.append(char)
            continue
        if char == ",":
            lookahead = index + 1
            while lookahead < len(text) and text[lookahead].isspace():
                lookahead += 1
            if lookahead < len(text) and text[lookahead] in "}]":
                continue
        output.append(char)
    return "".join(output)


def _balanced_json_objects(text: str) -> list[str]:
    """Return balanced ``{...}`` candidates while respecting quoted braces."""
    objects: list[str] = []
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(text[start : index + 1])
                start = None
    return objects


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
        on_stage: Callable[[dict[str, Any]], None] | None = None,
        max_attempts: int | None = None,
        llm_config: AgentModel | None = None,
    ) -> ReviewLoopResult:
        """Execute the review loop with model escalation.

        Returns a ``ReviewLoopResult`` with the (possibly fixed) code and
        full iteration history.
        """
        iterations: list[ReviewIterationRecord] = []
        total_attempts = 0
        last_errors: list[ManimError | dict] = []
        active_error_fingerprint: str | None = None
        active_episode: ErrorEpisode | None = None
        repair_memory: list[RepairAttempt] = []
        attempted_strategies: set[str] = set()
        pending_checkpoint: PendingPatchCheckpoint | None = None
        latest_validation_error: str | None = None

        for tier in self.tiers:
            for tier_attempt in range(tier.max_attempts):
                if max_attempts is not None and total_attempts >= max_attempts:
                    break
                next_attempt = total_attempts + 1

                reviewer = "visual" if config.uses_vision else "code"
                reuse_episode = (
                    pending_checkpoint is None
                    and active_episode is not None
                    and active_episode.source_revision == source_revision(code)
                )
                if reuse_episode:
                    # Revalidation already proved that this exact source
                    # revision advanced to this exact error. Re-rendering here
                    # can resurrect stale diagnostics and detach the prompt
                    # from the source that the reviewer is asked to patch.
                    errors = list(active_episode.errors)
                    frame_bytes = active_episode.frame_bytes
                    self._emit_stage(
                        on_stage,
                        {
                            "phase": "error_episode_resumed",
                            "reviewer": reviewer,
                            "attempt": next_attempt,
                            "model": tier.model,
                            "message": (
                                f"Tiếp tục error episode {active_episode.number} "
                                "từ kết quả revalidation đã xác nhận"
                            ),
                            "error_episode": active_episode.number,
                            "source_revision": active_episode.source_revision,
                            "error_fingerprint": active_episode.error_fingerprint,
                        },
                    )
                else:
                    self._emit_stage(
                        on_stage,
                        {
                            "phase": "validating",
                            "reviewer": reviewer,
                            "attempt": next_attempt,
                            "model": tier.model,
                            "message": f"Đang kiểm tra {reviewer} với {tier.model}",
                        },
                    )
                    # 1. Validate (run manim / VLM frame analysis)
                    try:
                        errors, frame_bytes = self._validate(
                            code,
                            config,
                            tier.model,
                            llm_config=llm_config,
                            reasoning_effort=tier.reasoning_effort,
                        )
                    except Exception as exc:
                        error_kind = "validation error" if config.uses_vision else "renderer error"
                        latest_validation_error = f"{error_kind}: {exc}"
                        logger.warning("Validation failed on model %s: %s", tier.model, exc)
                        record = ReviewIterationRecord(
                            iteration=len(iterations) + 1,
                            model=tier.model,
                            error_summary=f"Validation {error_kind}: {exc}",
                            escalated=True,
                            outcome="validation_error",
                            repair_history_count=len(repair_memory),
                        )
                        iterations.append(record)
                        if pending_checkpoint is not None:
                            # The candidate is still unproven. Spend the next
                            # configured validation slot on this exact
                            # checkpoint, without reporting a reviewer attempt
                            # that never happened.
                            continue
                        break  # escalate to next model

                if pending_checkpoint is not None:
                    checkpoint = pending_checkpoint
                    if code != checkpoint.candidate_code:
                        raise RuntimeError("Pending review checkpoint no longer matches source")
                    if not errors:
                        checkpoint.record.outcome = "resolved"
                        checkpoint.record.escalated = False
                        self._emit_stage(
                            on_stage,
                            {
                                "phase": "checkpoint_confirmed",
                                "reviewer": reviewer,
                                "attempt": next_attempt,
                                "model": tier.model,
                                "message": "Bản vá chờ xác nhận đã render thành công",
                            },
                        )
                        return ReviewLoopResult(
                            passed=True,
                            manim_code=code,
                            iterations=iterations,
                            total_attempts=total_attempts,
                        )
                    if _same_failure_site_after_patch(
                        checkpoint.previous_errors,
                        errors,
                        checkpoint.previous_code,
                        checkpoint.candidate_code,
                    ):
                        code = checkpoint.previous_code
                        errors = checkpoint.previous_errors
                        if (
                            active_episode is not None
                            and active_episode.source_revision == source_revision(code)
                        ):
                            frame_bytes = active_episode.frame_bytes
                        checkpoint.record.same_error = True
                        checkpoint.record.outcome = "same_error"
                        self._emit_stage(
                            on_stage,
                            {
                                "phase": "checkpoint_rolled_back",
                                "reviewer": reviewer,
                                "attempt": next_attempt,
                                "model": tier.model,
                                "message": (
                                    "Đã xác nhận lỗi cũ vẫn còn; chỉ rollback bản vá gần nhất"
                                ),
                                "error_fingerprint": checkpoint.error_fingerprint,
                            },
                        )
                    else:
                        checkpoint.record.outcome = "advanced_to_new_error"
                        new_fingerprint = error_fingerprint(errors, code)
                        previous_episode_number = active_episode.number if active_episode else 0
                        active_episode = ErrorEpisode(
                            number=previous_episode_number + 1,
                            source_revision=source_revision(code),
                            error_fingerprint=new_fingerprint,
                            errors=tuple(errors),
                            frame_bytes=frame_bytes,
                        )
                        self._emit_stage(
                            on_stage,
                            {
                                "phase": "checkpoint_confirmed",
                                "reviewer": reviewer,
                                "attempt": next_attempt,
                                "model": tier.model,
                                "message": "Bản vá trước đã xử lý lỗi cũ; tiếp tục với lỗi mới",
                                "error_episode": active_episode.number,
                                "source_revision": active_episode.source_revision,
                                "error_fingerprint": new_fingerprint,
                            },
                        )
                    pending_checkpoint = None

                latest_validation_error = None
                last_errors = errors

                if not errors:
                    return ReviewLoopResult(
                        passed=True,
                        manim_code=code,
                        iterations=iterations,
                        total_attempts=total_attempts,
                    )

                current_fingerprint = error_fingerprint(errors, code)
                if active_error_fingerprint and current_fingerprint != active_error_fingerprint:
                    self._emit_memory_reset(
                        on_stage,
                        reviewer=reviewer,
                        attempt=next_attempt,
                        model=tier.model,
                        previous=active_error_fingerprint,
                        current=current_fingerprint,
                    )
                    repair_memory.clear()
                    attempted_strategies.clear()
                active_error_fingerprint = current_fingerprint
                if (
                    active_episode is None
                    or active_episode.source_revision != source_revision(code)
                    or active_episode.error_fingerprint != current_fingerprint
                ):
                    previous_episode_number = active_episode.number if active_episode else 0
                    active_episode = ErrorEpisode(
                        number=previous_episode_number + 1,
                        source_revision=source_revision(code),
                        error_fingerprint=current_fingerprint,
                        errors=tuple(errors),
                        frame_bytes=frame_bytes,
                    )
                    self._emit_stage(
                        on_stage,
                        {
                            "phase": "error_episode_started",
                            "reviewer": reviewer,
                            "attempt": next_attempt,
                            "model": tier.model,
                            "message": f"Bắt đầu error episode {active_episode.number}",
                            "error_episode": active_episode.number,
                            "source_revision": active_episode.source_revision,
                            "error_fingerprint": current_fingerprint,
                        },
                    )

                # ``max_review_attempts`` counts actual reviewer requests, not
                # validation-only passes or checkpoint confirmation. This
                # keeps the displayed attempts aligned with the persisted
                # setting and with the number of LLM repair calls.
                total_attempts += 1

                record = ReviewIterationRecord(
                    iteration=len(iterations) + 1,
                    model=tier.model,
                    error_summary=self._error_summary(errors),
                    error_fingerprint=current_fingerprint,
                    repair_history_count=len(repair_memory),
                )

                runtime_api_context: dict[str, Any] | None = None
                if not config.uses_vision:
                    try:
                        runtime_api_context = build_runtime_api_context(code, errors)
                    except Exception:  # noqa: BLE001
                        # Introspection is valuable context, but a documentation
                        # failure must never prevent the existing repair path.
                        logger.warning("Unable to build runtime Manim API context", exc_info=True)
                    if runtime_api_context:
                        record.runtime_api_context = runtime_api_context
                        self._emit_stage(
                            on_stage,
                            {
                                "phase": "runtime_api_context",
                                "reviewer": reviewer,
                                "attempt": total_attempts,
                                "model": tier.model,
                                "message": (
                                    "Đã nạp API context từ Manim "
                                    f"{runtime_api_context.get('manim_version')} cho "
                                    f"{runtime_api_context.get('target_symbol')}"
                                ),
                                "runtime_api_context": runtime_api_context,
                            },
                        )
                        logger.info(
                            "Runtime Manim API context: version=%s target=%s exists=%s alternatives=%s",
                            runtime_api_context.get("manim_version"),
                            runtime_api_context.get("target_symbol"),
                            (runtime_api_context.get("exact_api") or {}).get("exists"),
                            [item.get("symbol") for item in runtime_api_context.get("alternatives", [])],
                        )

                # 2. Try to fix
                self._emit_stage(
                    on_stage,
                    {
                        "phase": "fixing",
                        "reviewer": reviewer,
                        "attempt": total_attempts,
                        "model": tier.model,
                        "message": f"Đang thực hiện fix bug lần {total_attempts} với {tier.model}",
                        "repair_history_count": len(repair_memory),
                    },
                )
                try:
                    fix = self._request_fix(
                        code,
                        errors,
                        config,
                        tier.model,
                        frame_bytes,
                        runtime_api_context=runtime_api_context,
                        repair_memory=repair_memory,
                        error_episode=active_episode.number if active_episode else 1,
                        error_fingerprint_value=current_fingerprint,
                        source_revision_value=source_revision(code),
                        llm_config=llm_config,
                        reasoning_effort=tier.reasoning_effort,
                    )
                except Exception as exc:
                    logger.warning(
                        "Fix request failed with LLM error on model %s: %s", tier.model, exc
                    )
                    record.escalated = tier_attempt + 1 >= tier.max_attempts
                    record.error_summary = f"{record.error_summary or ''}; LLM error: {exc}".strip(
                        "; "
                    )
                    record.outcome = "llm_error"
                    repair_memory.append(
                        RepairAttempt(
                            error_fingerprint=current_fingerprint,
                            model=tier.model,
                            outcome="llm_error",
                            explanation=str(exc)[:500],
                        )
                    )
                    iterations.append(record)
                    continue  # retry this tier until its configured budget is spent

                if fix is None:
                    record.escalated = tier_attempt + 1 >= tier.max_attempts
                    record.outcome = "invalid_reviewer_response"
                    repair_memory.append(
                        RepairAttempt(
                            error_fingerprint=current_fingerprint,
                            model=tier.model,
                            outcome="invalid_reviewer_response",
                        )
                    )
                    iterations.append(record)
                    continue  # retry this tier until its configured budget is spent

                if not fix.can_fix:
                    record.escalated = tier_attempt + 1 >= tier.max_attempts
                    record.outcome = "cannot_fix"
                    record.fix_applied = fix.explanation or None
                    repair_memory.append(
                        RepairAttempt(
                            error_fingerprint=current_fingerprint,
                            model=tier.model,
                            outcome="cannot_fix",
                            explanation=fix.explanation,
                        )
                    )
                    iterations.append(record)
                    logger.info(
                        "Model %s cannot fix; tier attempt %d/%d",
                        tier.model,
                        total_attempts,
                        tier.max_attempts,
                    )
                    continue  # retry this tier until its configured budget is spent

                strategy_fingerprint = semantic_strategy_fingerprint(
                    fix.original_code, fix.replacement_code
                )
                record.strategy_fingerprint = strategy_fingerprint

                # A deterministic guard backs up the prompt instruction: even
                # formatting-equivalent patches cannot be applied twice.
                if strategy_fingerprint in attempted_strategies:
                    reason = "Semantically equivalent repair strategy was already attempted"
                    record.strategy_guard_triggered = True
                    record.strategy_guard_reason = reason
                    record.outcome = "duplicate_strategy"
                    record.escalated = tier_attempt + 1 >= tier.max_attempts
                    repair_memory.append(
                        RepairAttempt(
                            error_fingerprint=current_fingerprint,
                            model=tier.model,
                            outcome="duplicate_strategy",
                            original_code=fix.original_code,
                            replacement_code=fix.replacement_code,
                            explanation=fix.explanation,
                            strategy_fingerprint=strategy_fingerprint,
                        )
                    )
                    iterations.append(record)
                    self._emit_stage(
                        on_stage,
                        {
                            "phase": "strategy_guard",
                            "reviewer": reviewer,
                            "attempt": total_attempts,
                            "model": tier.model,
                            "message": reason,
                            "strategy_fingerprint": strategy_fingerprint,
                        },
                    )
                    logger.info(
                        "Repair strategy guard rejected duplicate: error=%s strategy=%s model=%s",
                        current_fingerprint,
                        strategy_fingerprint,
                        tier.model,
                    )
                    continue

                attempted_strategies.add(strategy_fingerprint)

                # 3. Apply a verified local replacement only. Never let a
                # reviewer rewrite the full scene after seeing its context.
                rejection_reason = validate_partial_fix(
                    code, fix.original_code, fix.replacement_code
                )
                if rejection_reason is not None:
                    record.escalated = tier_attempt + 1 >= tier.max_attempts
                    record.error_summary = (
                        f"{record.error_summary or ''}; rejected reviewer patch: "
                        f"{rejection_reason}"
                    ).strip("; ")
                    record.outcome = "patch_rejected"
                    repair_memory.append(
                        RepairAttempt(
                            error_fingerprint=current_fingerprint,
                            model=tier.model,
                            outcome="patch_rejected",
                            original_code=fix.original_code,
                            replacement_code=fix.replacement_code,
                            explanation=f"{fix.explanation}; {rejection_reason}".strip("; "),
                            strategy_fingerprint=strategy_fingerprint,
                        )
                    )
                    iterations.append(record)
                    self._emit_stage(
                        on_stage,
                        {
                            "phase": "patch_rejected",
                            "reviewer": reviewer,
                            "attempt": total_attempts,
                            "model": tier.model,
                            "message": f"Đã từ chối patch không cục bộ: {rejection_reason}",
                            "strategy_fingerprint": strategy_fingerprint,
                        },
                    )
                    continue  # retry this tier with the recorded rejection context

                prev_code = code
                code = apply_partial_fix(code, fix.original_code, fix.replacement_code)
                record.fix_applied = fix.explanation
                record.original_code = fix.original_code
                record.replacement_code = fix.replacement_code
                self._emit_stage(
                    on_stage,
                    {
                        "phase": "patch_applied",
                        "reviewer": reviewer,
                        "attempt": total_attempts,
                        "model": tier.model,
                        "message": "Đã áp dụng thay thế cục bộ do reviewer đề xuất",
                        "original_code": fix.original_code,
                        "replacement_code": fix.replacement_code,
                        "explanation": fix.explanation,
                        "strategy_fingerprint": strategy_fingerprint,
                    },
                )

                # 4. Re-validate
                try:
                    new_errors, new_frame_bytes = self._validate(
                        code,
                        config,
                        tier.model,
                        llm_config=llm_config,
                        reasoning_effort=tier.reasoning_effort,
                    )
                except Exception as exc:
                    latest_validation_error = f"re-validation error: {exc}"
                    logger.warning(
                        "Re-validation was inconclusive on model %s: %s", tier.model, exc
                    )
                    record.escalated = tier_attempt + 1 >= tier.max_attempts
                    record.outcome = "revalidation_error"
                    record.error_summary = (
                        f"{record.error_summary or ''}; re-validation infrastructure error: {exc}"
                    ).strip("; ")
                    repair_memory.append(
                        RepairAttempt(
                            error_fingerprint=current_fingerprint,
                            model=tier.model,
                            outcome="revalidation_error",
                            original_code=fix.original_code,
                            replacement_code=fix.replacement_code,
                            explanation=fix.explanation,
                            strategy_fingerprint=strategy_fingerprint,
                        )
                    )
                    iterations.append(record)
                    pending_checkpoint = PendingPatchCheckpoint(
                        previous_code=prev_code,
                        candidate_code=code,
                        previous_errors=errors,
                        error_fingerprint=current_fingerprint,
                        record=record,
                    )
                    # There is no evidence that the patch reintroduced error A.
                    # Keep the candidate checkpoint and use the next configured
                    # attempt (same tier when available) to validate it first.
                    continue

                if not new_errors:
                    record.outcome = "resolved"
                    iterations.append(record)
                    return ReviewLoopResult(
                        passed=True,
                        manim_code=code,
                        iterations=iterations,
                        total_attempts=total_attempts,
                    )

                last_errors = new_errors
                new_fingerprint = error_fingerprint(new_errors, code)

                # The same root error remains unresolved. Remember the failed
                # strategy, revert it, and ensure the next attempt sees it.
                if _same_failure_site_after_patch(errors, new_errors, prev_code, code):
                    record.same_error = True
                    record.escalated = tier_attempt + 1 >= tier.max_attempts
                    record.outcome = "same_error"
                    code = prev_code  # revert unsuccessful fix
                    repair_memory.append(
                        RepairAttempt(
                            error_fingerprint=current_fingerprint,
                            model=tier.model,
                            outcome="same_error",
                            original_code=fix.original_code,
                            replacement_code=fix.replacement_code,
                            explanation=fix.explanation,
                            strategy_fingerprint=strategy_fingerprint,
                        )
                    )
                    iterations.append(record)
                    logger.info(
                        "Same error persists after fix by %s; history now has %d attempt(s)",
                        tier.model,
                        len(repair_memory),
                    )
                    continue

                # The previous error was fixed and execution advanced to a new
                # error. Keep the code, retain the full audit trail, but reset
                # active repair memory exactly as requested.
                record.outcome = "advanced_to_new_error"
                iterations.append(record)
                self._emit_memory_reset(
                    on_stage,
                    reviewer=reviewer,
                    attempt=total_attempts,
                    model=tier.model,
                    previous=current_fingerprint,
                    current=new_fingerprint,
                )
                repair_memory.clear()
                attempted_strategies.clear()
                active_error_fingerprint = new_fingerprint
                previous_episode_number = active_episode.number if active_episode else 0
                active_episode = ErrorEpisode(
                    number=previous_episode_number + 1,
                    source_revision=source_revision(code),
                    error_fingerprint=new_fingerprint,
                    errors=tuple(new_errors),
                    frame_bytes=new_frame_bytes,
                )
                self._emit_stage(
                    on_stage,
                    {
                        "phase": "error_episode_started",
                        "reviewer": reviewer,
                        "attempt": total_attempts,
                        "model": tier.model,
                        "message": f"Bắt đầu error episode {active_episode.number}",
                        "error_episode": active_episode.number,
                        "source_revision": active_episode.source_revision,
                        "error_fingerprint": new_fingerprint,
                    },
                )

        # All tiers exhausted
        if pending_checkpoint is not None:
            pending_checkpoint.record.outcome = "candidate_unvalidated"
            final_err = (
                "Candidate patch could not be conclusively re-validated"
                f": {latest_validation_error or 'validation attempts exhausted'}"
            )
        elif iterations and iterations[-1].outcome == "validation_error":
            final_err = latest_validation_error or "Validation failed"
        else:
            final_err = self._error_summary(last_errors) if last_errors else None
        return ReviewLoopResult(
            passed=False,
            manim_code=code,
            iterations=iterations,
            total_attempts=total_attempts,
            final_error=final_err,
        )

    @staticmethod
    def _emit_stage(callback: Callable[[dict[str, Any]], None] | None, stage: dict[str, Any]) -> None:
        if callback is None:
            return
        try:
            callback(stage)
        except Exception:  # noqa: BLE001
            logger.warning("Unable to publish review stage", exc_info=True)

    @classmethod
    def _emit_memory_reset(
        cls,
        callback: Callable[[dict[str, Any]], None] | None,
        *,
        reviewer: str,
        attempt: int,
        model: str,
        previous: str,
        current: str,
    ) -> None:
        logger.info("Repair memory reset: resolved=%s next=%s", previous, current)
        cls._emit_stage(
            callback,
            {
                "phase": "repair_memory_reset",
                "reviewer": reviewer,
                "attempt": attempt,
                "model": model,
                "message": "Lỗi trước đã được sửa; repair memory đã reset cho lỗi kế tiếp",
                "previous_error_fingerprint": previous,
                "error_fingerprint": current,
            },
        )

    # -- private: validation ------------------------------------------------

    def _validate(
        self,
        code: str,
        config: ReviewConfig,
        model: str,
        *,
        llm_config: AgentModel | None = None,
        reasoning_effort: str = "none",
    ) -> tuple[list[ManimError | dict], bytes | None]:
        """Validate code by running manim.

        For code review: parse stderr errors.
        For visual review: render with -s and send frame to VLM.
        """
        from app.renderer import ManimProcessTimeout, UnsafeManimCode

        try:
            render = render_manim_for_validation(code, extra_flags=config.render_flags)
        except UnsafeManimCode as exc:
            import re

            msg = str(exc)
            m = re.search(r"line (\d+)", msg)
            line = int(m.group(1)) if m else None
            return [ManimError(line=line, message=msg)], None
        except ManimProcessTimeout as exc:
            diagnostics = "\n".join(part for part in (exc.stderr, exc.stdout) if part).strip()
            return [
                ManimError(
                    line=None,
                    message=(diagnostics or str(exc))[-4_000:],
                )
            ], None

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
                return [
                    ManimError(line=None, message="Manim succeeded but no frame was saved")
                ], None

            issues = self._vlm_analyse_frame(
                frame_bytes,
                code,
                config,
                model,
                temperature=llm_config.temperature if llm_config else 0.1,
                max_tokens=llm_config.max_tokens if llm_config else 4096,
                reasoning_effort=reasoning_effort,
            )
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
        *,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        reasoning_effort: str = "none",
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
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        )
        parsed = next(
            (
                candidate
                for candidate in _parse_json_objects(raw)
                if isinstance(candidate.get("has_issues"), bool)
            ),
            {},
        )
        has_issues = parsed.get("has_issues")
        if not isinstance(has_issues, bool):
            raise ValueError("Visual reviewer returned an invalid has_issues verdict")
        if not has_issues:
            return []
        issues = parsed.get("issues", [])
        if not isinstance(issues, list) or not issues or not all(
            isinstance(issue, dict) for issue in issues
        ):
            raise ValueError("Visual reviewer reported issues without a valid issues list")
        return issues

    # -- private: fix -------------------------------------------------------

    def _request_fix(
        self,
        code: str,
        errors: list[ManimError | dict],
        config: ReviewConfig,
        model: str,
        frame_bytes: bytes | None,
        *,
        runtime_api_context: dict[str, Any] | None = None,
        repair_memory: list[RepairAttempt] | None = None,
        error_episode: int = 1,
        error_fingerprint_value: str = "",
        source_revision_value: str = "",
        llm_config: AgentModel | None = None,
        reasoning_effort: str = "none",
    ) -> CodeFix | None:
        """Ask an LLM to produce a partial code fix."""
        error_text = "\n".join(
            f"  Line {e.line if isinstance(e, ManimError) else e.get('line', '?')}: "
            f"{e.message if isinstance(e, ManimError) else e.get('message', e.get('description', str(e)))}"
            for e in errors
        )
        runtime_section = format_runtime_api_context(runtime_api_context)
        history_section = self._format_repair_memory(repair_memory or [])
        prompt_sections = [
            (
                "<CURRENT_ERROR_EPISODE "
                f'number="{error_episode}" '
                f'error_fingerprint="{error_fingerprint_value}" '
                f'source_revision="{source_revision_value}">\n'
                "Fix only the traceback in this episode against the source revision below. "
                "Errors from earlier episodes are already resolved; do not recreate or patch them.\n"
                "</CURRENT_ERROR_EPISODE>"
            ),
            f"Source code:\n```python\n{code}\n```\n\n"
            f"Errors / issues found:\n{error_text}"
        ]
        if runtime_section:
            prompt_sections.append(runtime_section)
        if history_section:
            prompt_sections.append(history_section)
        prompt_sections.append(
            "Provide one exact, unique source excerpt and its replacement only. "
            "Do not return the full file. The excerpt and replacement must each be "
            "at most 12 lines and no more than 20% of the source. "
            "Choose a strategy that is not semantically equivalent to a failed attempt above."
        )
        user_msg = "\n\n".join(prompt_sections)

        if config.uses_vision and frame_bytes:
            raw = self.llm.complete_with_image(
                messages=[
                    {"role": "system", "content": config.fix_prompt},
                    {"role": "user", "content": user_msg},
                ],
                image_bytes=frame_bytes,
                model=model,
                temperature=llm_config.temperature if llm_config else 0.1,
                max_tokens=llm_config.max_tokens if llm_config else 4096,
                reasoning_effort=reasoning_effort,
            )
        else:
            raw = self.llm.complete(
                messages=[
                    {"role": "system", "content": config.fix_prompt},
                    {"role": "user", "content": user_msg},
                ],
                model=model,
                temperature=llm_config.temperature if llm_config else 0.1,
                max_tokens=llm_config.max_tokens if llm_config else 4096,
                reasoning_effort=reasoning_effort,
            )

        fix = self._decode_code_fix(raw)
        if fix is not None:
            return fix

        logger.warning(
            "Reviewer returned invalid structured output on model %s; requesting one format repair: %r",
            model,
            raw[:1_000],
        )
        normalized = self.llm.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Normalize the supplied reviewer response into exactly one JSON object with "
                        "these fields and types: can_fix (boolean), original_code (string), "
                        "replacement_code (string), explanation (string). Preserve the proposed "
                        "code verbatim and escape newlines inside JSON strings. Do not add markdown "
                        "or invent a repair. If the response cannot be recovered, return "
                        '{"can_fix":false,"original_code":"","replacement_code":"",'
                        '"explanation":"Unrecoverable reviewer response"}.'
                    ),
                },
                {"role": "user", "content": raw[:12_000]},
            ],
            model=model,
            temperature=0,
            max_tokens=llm_config.max_tokens if llm_config else 4096,
            reasoning_effort=reasoning_effort,
        )
        return self._decode_code_fix(normalized)

    @staticmethod
    def _decode_code_fix(raw: str) -> CodeFix | None:
        for parsed in _parse_json_objects(raw):
            can_fix = parsed.get("can_fix")
            original_code = parsed.get("original_code")
            replacement_code = parsed.get("replacement_code")
            explanation = parsed.get("explanation")
            if not isinstance(can_fix, bool) or not all(
                isinstance(value, str)
                for value in (original_code, replacement_code, explanation)
            ):
                continue
            return CodeFix(
                can_fix=can_fix,
                original_code=original_code,
                replacement_code=replacement_code,
                explanation=explanation,
            )
        return None

    @staticmethod
    def _format_repair_memory(memory: list[RepairAttempt]) -> str:
        if not memory:
            return ""
        lines = [
            "<REPAIR_ATTEMPT_MEMORY>",
            "These attempts belong to this same unresolved error. Do not repeat them, even with different formatting.",
        ]
        for index, attempt in enumerate(memory[-8:], start=max(1, len(memory) - 7)):
            lines.append(
                f"Attempt {index}: model={attempt.model}; outcome={attempt.outcome}; "
                f"strategy={attempt.strategy_fingerprint or 'none'}"
            )
            if attempt.original_code or attempt.replacement_code:
                lines.append(f"  original: {attempt.original_code[:1_000]}")
                lines.append(f"  replacement: {attempt.replacement_code[:1_000]}")
            if attempt.explanation:
                lines.append(f"  explanation: {attempt.explanation[:500]}")
        lines.append("</REPAIR_ATTEMPT_MEMORY>")
        return "\n".join(lines)[:8_000]

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
