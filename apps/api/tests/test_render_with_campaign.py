"""Tests de renderizado con reglas de campaña (grafo FFmpeg + render real)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from winclip.core.config import Settings
from winclip.core.ids import new_project_id
from winclip.core.storage import LocalStorage
from winclip.pipeline.render import (
    WATERMARK_MARGIN,
    WATERMARK_MAX_WIDTH,
    WATERMARK_TOP,
    RenderError,
    apply_campaign_to_render_options,
    build_cta_card,
    build_ffmpeg_command,
    build_filter_graph,
    render_clip,
)
from winclip.pipeline.render_models import RenderOptions
from winclip.pipeline.schemas import Transcript, TranscriptSegment, WordTimestamp
from winclip.pipeline.select import CandidatesDocument, ClipCandidate
from winclip.pipeline.subtitles.fonts import resolve_font
from winclip.rules.schema import CampaignRules


def _write_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (120, 60), (245, 158, 11, 255)).save(path, format="PNG")
    return path


def test_apply_campaign_to_render_options_applies_visual_rules(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "storage")
    wm_rel = "campaigns/watermarks/01brand.png"
    wm_abs = _write_png(storage.resolve_safe(wm_rel))

    rules = CampaignRules(
        name="Marca Pro",
        subtitle_preset="hormozi",
        hook_max_seconds=2,
        cta_text="Sigue el canal para más",
        watermark_path=wm_rel,
    )
    opts = apply_campaign_to_render_options(RenderOptions(), rules, storage=storage)

    assert opts.preset == "hormozi"
    assert opts.hook_seconds == 2.0
    assert opts.cta_text == "Sigue el canal para más"
    assert opts.watermark_path == wm_abs


def test_apply_campaign_to_render_options_rejects_traversal(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "storage")
    rules = CampaignRules.model_construct(
        name="Maliciosa",
        watermark_path="../../etc/passwd.png",
        hook_max_seconds=3,
        subtitle_preset=None,
        cta_text=None,
    )
    with pytest.raises(RenderError, match="watermark_path inválido"):
        apply_campaign_to_render_options(RenderOptions(), rules, storage=storage)


def test_filter_graph_and_command_include_watermark_hook_and_cta(tmp_path: Path) -> None:
    hook_png = _write_png(tmp_path / "hook.png")
    wm_png = _write_png(tmp_path / "wm.png")
    cta_png = _write_png(tmp_path / "cta.png")
    subs = tmp_path / "subs.ass"
    subs.write_text("", encoding="utf-8")
    script = tmp_path / "graph.txt"

    graph = build_filter_graph(
        "[0:v]scale=1080:1920[vref]",
        fps=30,
        engine="ass",
        subtitles_path=subs,
        fonts_dir=tmp_path,
        hook_input=1,
        hook_seconds=2.0,
        watermark_input=2,
        overlay_input=None,
        has_audio=True,
        cta_input=3,
        cta_start=7.0,
    )

    assert "enable='lt(t,2.000)'" in graph
    assert f"scale={WATERMARK_MAX_WIDTH}:-2" in graph
    assert f"overlay=W-w-{WATERMARK_MARGIN}:{WATERMARK_TOP}[vwm]" in graph
    assert "enable='gte(t,7.000)'[vcta]" in graph

    cmd, hook_idx, wm_idx, overlay_idx = build_ffmpeg_command(
        Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"),
        tmp_path / "src.mp4",
        start=0.0,
        duration=10.0,
        fps=30,
        filter_script=script,
        graph=graph,
        target=tmp_path / "out.mp4",
        encoder="libx264",
        hook_card=hook_png,
        watermark=wm_png,
        overlay=False,
        has_audio=True,
        cta_card=cta_png,
    )
    assert hook_idx == 1
    assert wm_idx == 2
    assert overlay_idx is None
    assert str(cta_png) in cmd
    assert str(wm_png) in cmd


def test_build_cta_card_creates_rgba_png(tmp_path: Path) -> None:
    font = resolve_font(
        "Montserrat ExtraBold",
        fallback="Inter",
        settings=Settings(_env_file=None),
    ).font.path
    card = build_cta_card(
        "Suscríbete hoy al canal",
        tmp_path / "cta.png",
        font_path=font,
        font_size=64,
    )
    assert card.is_file()
    with Image.open(card) as img:
        assert img.size == (1080, 1920)
        assert img.mode == "RGBA"


def test_real_render_clip_with_campaign_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")
    if not Path(settings.ffmpeg_bin).is_file():
        pytest.skip("FFMPEG_BIN no disponible")
    monkeypatch.setattr("winclip.pipeline.render.detect_video_encoder", lambda _s: "libx264")

    storage = LocalStorage(settings.storage_dir)
    project_id = new_project_id()
    storage.ensure_project_dirs(project_id)

    # Generar video fuente sintético corto (4s, 640x360 + audio sine)
    source = storage.source_dir(project_id) / "original.mp4"
    proc = subprocess.run(
        [
            str(settings.ffmpeg_bin),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x1e293b:s=640x360:d=4:r=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

    transcript = Transcript(
        language="es",
        duration=4.0,
        model="test",
        segments=[
            TranscriptSegment(
                id=0,
                start=0.2,
                end=3.5,
                text="Hola mundo finanzas",
                words=[
                    WordTimestamp(w="Hola", s=0.2, e=1.0, p=0.99),
                    WordTimestamp(w="mundo", s=1.1, e=2.0, p=0.99),
                    WordTimestamp(w="finanzas", s=2.1, e=3.5, p=0.99),
                ],
            )
        ],
    )
    storage.write_json_atomic(storage.transcript_path(project_id), transcript)

    candidate = ClipCandidate(
        id="cand01",
        start=0.0,
        end=3.8,
        title="Clip con campaña",
        hook="Gancho rápido",
        description="Descripción",
        hashtags=["#finanzas"],
        score=92,
        reason="test",
        language="es",
    )
    storage.write_json_atomic(
        storage.selection_path(project_id),
        CandidatesDocument(
            project_id=project_id,
            campaign_id="camp01",
            requested=1,
            provider="test",
            candidates=[candidate],
        ),
    )

    wm_rel = "campaigns/watermarks/01testwm.png"
    _write_png(storage.resolve_safe(wm_rel))
    rules = CampaignRules(
        name="Campaña Render",
        subtitle_preset="hormozi",
        hook_max_seconds=2,
        cta_text="Episodio completo en el canal",
        watermark_path=wm_rel,
    )

    manifest = render_clip(
        project_id,
        "cand01",
        RenderOptions(reframe="center"),
        settings=settings,
        campaign_rules=rules,
    )

    assert manifest.subtitles.preset == "hormozi"
    assert manifest.hook_overlay is True
    clip_dir = storage.clip_dir(project_id, manifest.clip_id)
    assert (clip_dir / "clip.mp4").stat().st_size > 0
    assert (clip_dir / "thumb.jpg").stat().st_size > 0
    assert (clip_dir / "render.json").is_file()
