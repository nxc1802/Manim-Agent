from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from ai_engine.agents.code_reviewer import run_code_reviewer
from ai_engine.config import (
    load_agent_models_yaml,
    load_builder_review_loop,
    resolve_agent_params,
)
from ai_engine.llm_client import FakeLLMClient
from ai_engine.orchestrator import run_single_review_round
from backend.core.config import settings
from backend.services.code_sandbox import SandboxLimits
from backend.services.frame_info import extract_end_of_play_jpeg_frame

_EXAMPLE_MODELS = Path(__file__).resolve().parents[3] / (
    "ai_engine/config/agent_models.example.yaml"
)


@pytest.mark.anyio
async def test_run_code_reviewer_parses_fake() -> None:
    issue = '{"issues":[{"severity":"info","code":"n","message":"ok"}]}'
    llm = FakeLLMClient(code_review_json=issue)
    data = load_agent_models_yaml(_EXAMPLE_MODELS)
    p = resolve_agent_params(data, "code_reviewer")
    res, _pv, _m, _s, _u = await run_code_reviewer(
        llm=llm,
        model=p.model,
        temperature=p.temperature,
        max_tokens=p.max_tokens,
        manim_code="x=1\n",
    )
    assert len(res.issues) == 1


def _tiny_mp4(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x240:d=0.4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        timeout=60,
    )


@pytest.mark.anyio
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
async def test_review_round_early_stop_with_preview(tmp_path: Path) -> None:
    video = tmp_path / "p.mp4"
    _tiny_mp4(video)
    data = load_agent_models_yaml(_EXAMPLE_MODELS)
    cfg = load_builder_review_loop(data)
    llm = FakeLLMClient()
    code = """from __future__ import annotations
from manim import Scene
class GeneratedScene(Scene):
    def construct(self) -> None:
        self.wait(0.1)
"""
    code_llm = resolve_agent_params(data, "code_reviewer")
    visual_llm = resolve_agent_params(data, "visual_reviewer")
    rep = await run_single_review_round(
        llm=llm,
        review_cfg=cfg,
        code_llm=code_llm,
        visual_llm=visual_llm,
        manim_code=code,
        sandbox_limits=SandboxLimits(max_bytes=settings.max_manim_code_bytes),
        preview_video_path=video,
        extract_preview_frame=extract_end_of_play_jpeg_frame,
    )
    assert rep.code_review_passed
    assert rep.visual_review is not None
    assert rep.visual_review_passed is True
    assert rep.early_stop is True


@pytest.mark.anyio
async def test_review_round_skips_visual_without_preview() -> None:
    data = load_agent_models_yaml(_EXAMPLE_MODELS)
    cfg = load_builder_review_loop(data)
    llm = FakeLLMClient(
        code_review_json='{"issues":[{"severity":"error","code":"x","message":"bad"}]}',
    )
    code = """from __future__ import annotations
from manim import Scene
class GeneratedScene(Scene):
    def construct(self) -> None:
        self.wait(0.1)
"""
    code_llm = resolve_agent_params(data, "code_reviewer")
    visual_llm = resolve_agent_params(data, "visual_reviewer")
    rep = await run_single_review_round(
        llm=llm,
        review_cfg=cfg,
        code_llm=code_llm,
        visual_llm=visual_llm,
        manim_code=code,
        sandbox_limits=SandboxLimits(max_bytes=settings.max_manim_code_bytes),
        preview_video_path=None,
        extract_preview_frame=extract_end_of_play_jpeg_frame,
    )
    assert not rep.code_review_passed
    assert rep.visual_review is None
    assert rep.visual_review_skipped_reason == "no_preview_video"
    assert rep.early_stop is False


@pytest.mark.anyio
async def test_review_round_skips_visual_when_disabled() -> None:
    data = load_agent_models_yaml(_EXAMPLE_MODELS)
    # Force disabled
    raw = data["builder_review_loop"]
    raw["visual_reviewer_enabled"] = False
    cfg = load_builder_review_loop(data)

    llm = FakeLLMClient()
    code = """from __future__ import annotations
from manim import Scene
class GeneratedScene(Scene):
    def construct(self) -> None:
        self.wait(0.1)
"""
    code_llm = resolve_agent_params(data, "code_reviewer")
    visual_llm = resolve_agent_params(data, "visual_reviewer")
    rep = await run_single_review_round(
        llm=llm,
        review_cfg=cfg,
        code_llm=code_llm,
        visual_llm=visual_llm,
        manim_code=code,
        sandbox_limits=SandboxLimits(max_bytes=settings.max_manim_code_bytes),
        preview_video_path=Path("/tmp/fake.mp4"),
        extract_preview_frame=extract_end_of_play_jpeg_frame,
    )
    assert rep.code_review_passed
    assert rep.visual_review is None
    assert rep.visual_review_skipped_reason == "disabled_in_config"
    assert rep.visual_review_passed is None
    assert (
        rep.early_stop is True
    )  # Because only code_review_passed is required in default (wait, default requires both?)


@pytest.mark.anyio
async def test_review_round_dynamic_early_stop() -> None:
    data = load_agent_models_yaml(_EXAMPLE_MODELS)
    # Require both
    raw = data["builder_review_loop"]
    raw["visual_reviewer_enabled"] = False
    raw["early_stop"]["require_all"] = ["code_review_passed", "visual_review_passed"]
    cfg = load_builder_review_loop(data)

    llm = FakeLLMClient()
    code = """from __future__ import annotations
from manim import Scene
class GeneratedScene(Scene):
    def construct(self) -> None:
        self.wait(0.1)
"""
    code_llm = resolve_agent_params(data, "code_reviewer")
    visual_llm = resolve_agent_params(data, "visual_reviewer")
    rep = await run_single_review_round(
        llm=llm,
        review_cfg=cfg,
        code_llm=code_llm,
        visual_llm=visual_llm,
        manim_code=code,
        sandbox_limits=SandboxLimits(max_bytes=settings.max_manim_code_bytes),
        preview_video_path=Path("/tmp/fake.mp4"),
        extract_preview_frame=extract_end_of_play_jpeg_frame,
    )
    assert rep.code_review_passed
    assert rep.visual_review_passed is None
    # visual_review_passed is None, but pass_results treats it as True for requirement check if skipped?
    # No, my logic was: "visual_review_passed": visual_passed if visual_passed is not None else True
    assert rep.early_stop is True
