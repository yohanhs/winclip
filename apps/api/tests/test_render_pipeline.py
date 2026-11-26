"""Tests del orquestador de render: filtros, progreso, huella e idempotencia."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from winclip.core.config import Settings
from winclip.core.storage import LocalStorage
from winclip.pipeline import render as render_module
from winclip.pipeline.render import (
    RenderError,
    _is_fresh,
    _publish,
    build_filter_graph,
    build_hook_card,
    compute_fingerprint,
    detect_video_encoder,
    encoder_arguments,
    find_existing_clip,
    output_fps,
    parse_progress_line,
    render_clip,
    render_project_clips,
)
from winclip.pipeline.render_models import (
    FINGERPRINT_FILENAME,
    MANIFEST_FILENAME,
    OUTPUT_FILENAME,
    SUBTITLES_FILENAME,
    THUMBNAIL_FILENAME,
    RenderManifest,
    RenderOptions,
)
from winclip.pipeline.select import CandidateProposal, CandidatesDocument, ClipCandidate
from winclip.pipeline.subtitles.fonts import resolve_font
from winclip.pipeline.subtitles.presets import load_preset


def _candidate(candidate_id: str = "01jcand", hook: str = "Mira esto ahora") -> ClipCandidate:
    return ClipCandidate(
        id=candidate_id,
        start=1.0,
        end=5.0,
        title="t",
        hook=hook,
        description="d",
        hashtags=["#x"],
        score=90,
        reason="r",
        language="es",
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        storage_dir=tmp_path / "storage",
        user_fonts_dir=tmp_path / "fuentes",
    )


def test_parse_progress_line() -> None:
    assert parse_progress_line("out_time_us=1500000") == 1.5
    assert parse_progress_line("frame=42") is None
    assert parse_progress_line("out_time_us=no") is None
    assert parse_progress_line("progress=continue") is None


@pytest.mark.parametrize(
    ("source", "expected"),
    [(60.0, 30.0), (29.97, 30.0), (23.976, 24.0), (25.0, 25.0), (None, 30.0), (0.0, 30.0)],
)
def test_output_fps(source: float | None, expected: float) -> None:
    assert output_fps(source) == expected


def test_encoder_arguments() -> None:
    hardware = encoder_arguments("h264_videotoolbox")
    assert hardware[0:2] == ["-c:v", "h264_videotoolbox"]
    assert "-b:v" in hardware

    software = encoder_arguments("libx264")
    assert software[0:2] == ["-c:v", "libx264"]
    assert "-crf" in software


def test_detect_video_encoder_falls_back(ffmpeg_settings: Settings) -> None:
    assert detect_video_encoder(ffmpeg_settings) in {"h264_videotoolbox", "libx264"}


def test_filter_graph_with_ass_subs_and_audio() -> None:
    graph = build_filter_graph(
        "[0:v]scale=1080:1920[vref]",
        fps=30,
        engine="ass",
        subtitles_path=Path("/tmp/subs.ass"),
        fonts_dir=Path("/tmp/fonts"),
        hook_input=1,
        hook_seconds=3.0,
        watermark_input=2,
        overlay_input=None,
        has_audio=True,
    )

    assert "ass=filename='/tmp/subs.ass':fontsdir='/tmp/fonts'" in graph
    assert "enable='lt(t,3.000)'" in graph
    assert "fade=t=out:st=2.700" in graph
    assert "overlay=W-w-48:120" in graph
    assert "loudnorm=I=-14:TP=-1.5:LRA=11" in graph
    assert "[vout]" in graph
    assert "[aout]" in graph


def test_filter_graph_pil_overlay_and_no_audio() -> None:
    graph = build_filter_graph(
        "[0:v]crop=w=608:h=1080:x=0.00:y=0[vref]",
        fps=30,
        engine="pil",
        subtitles_path=Path("/tmp/subs.ass"),
        fonts_dir=Path("/tmp/fonts"),
        hook_input=None,
        hook_seconds=3.0,
        watermark_input=None,
        overlay_input=1,
        has_audio=False,
    )

    assert "[1:v]format=rgba[subs]" in graph
    assert "overlay=0:0:format=auto" in graph
    assert "[aout]" not in graph
    assert "ass=" not in graph


def test_build_hook_card_is_png_with_content(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    preset = load_preset("bold-yellow")
    font = resolve_font(preset.font, fallback=preset.fallback_font, settings=settings)

    card = build_hook_card(
        "Este es un hook bastante largo que debería partirse en varias líneas",
        tmp_path / "hook.png",
        font_path=font.font.path,
        font_size=70,
    )

    from PIL import Image

    image = Image.open(card)
    assert image.size == (1080, 1920)
    opaque_rows = [
        y
        for y in range(0, 1920, 20)
        if image.getpixel((540, y))[3] > 0  # type: ignore[index]
    ]
    assert opaque_rows
    assert min(opaque_rows) < 1920 * 0.25


def test_fingerprint_is_stable_and_sensitive(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    source = tmp_path / "original.mp4"
    source.write_bytes(b"video")
    candidate = _candidate()
    preset = load_preset("bold-yellow")
    font = resolve_font(preset.font, fallback=preset.fallback_font, settings=settings)

    base = compute_fingerprint(
        source,
        candidate,
        options=RenderOptions(),
        preset=preset,
        font=font,
        fps=30.0,
    )
    again = compute_fingerprint(
        source,
        candidate,
        options=RenderOptions(),
        preset=preset,
        font=font,
        fps=30.0,
    )
    assert base == again

    other_preset = load_preset("mrbeast")
    changed = compute_fingerprint(
        source,
        candidate,
        options=RenderOptions(preset="mrbeast"),
        preset=other_preset,
        font=font,
        fps=30.0,
    )
    assert changed != base

    forced = compute_fingerprint(
        source,
        candidate,
        options=RenderOptions(force=True),
        preset=preset,
        font=font,
        fps=30.0,
    )
    # `--force` no forma parte de la huella: solo evita el atajo de idempotencia.
    assert forced == base

    source.write_bytes(b"video distinto")
    assert (
        compute_fingerprint(
            source,
            candidate,
            options=RenderOptions(),
            preset=preset,
            font=font,
            fps=30.0,
        )
        != base
    )


def _write_manifest(directory: Path, candidate_id: str) -> RenderManifest:
    directory.mkdir(parents=True, exist_ok=True)
    for name in (OUTPUT_FILENAME, THUMBNAIL_FILENAME, SUBTITLES_FILENAME):
        (directory / name).write_bytes(b"contenido")
    manifest = RenderManifest(
        clip_id=directory.name,
        candidate_id=candidate_id,
        width=1080,
        height=1920,
        fps=30,
        reframe={"mode": "face", "track": [[0.0, 0.5]]},
        subtitles={"engine": "ass", "preset": "bold-yellow", "font": "Montserrat ExtraBold"},
        hook_overlay=True,
        duration=4.0,
        output=OUTPUT_FILENAME,
        thumbnail=THUMBNAIL_FILENAME,
    )
    (directory / MANIFEST_FILENAME).write_text(manifest.model_dump_json(), encoding="utf-8")
    return manifest


def test_find_existing_clip_and_freshness(tmp_path: Path) -> None:
    clips_dir = tmp_path / "clips"
    clip_dir = clips_dir / "01jclip"
    _write_manifest(clip_dir, "01jcand")
    (clip_dir / FINGERPRINT_FILENAME).write_text("abc\n", encoding="utf-8")

    assert find_existing_clip(clips_dir, "01jcand") == clip_dir
    assert find_existing_clip(clips_dir, "01jotro") is None
    assert _is_fresh(clip_dir, "abc") is True
    assert _is_fresh(clip_dir, "otro") is False

    (clip_dir / THUMBNAIL_FILENAME).unlink()
    assert _is_fresh(clip_dir, "abc") is False


def test_publish_replaces_existing_directory_atomically(tmp_path: Path) -> None:
    clips_dir = tmp_path / "clips"
    target = clips_dir / "01jclip"
    target.mkdir(parents=True)
    (target / "viejo.txt").write_text("viejo", encoding="utf-8")
    staging = clips_dir / ".tmp-nuevo"
    staging.mkdir()
    (staging / "nuevo.txt").write_text("nuevo", encoding="utf-8")

    _publish(staging, target, clips_dir)

    assert (target / "nuevo.txt").is_file()
    assert not (target / "viejo.txt").exists()
    assert not list(clips_dir.glob(".old-*"))


def test_render_project_clips_validates_flag_combinations(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with pytest.raises(RenderError, match="no ambos"):
        render_project_clips(
            "proyecto",
            options=RenderOptions(),
            all_clips=True,
            candidate_ids=["x"],
            settings=settings,
        )
    with pytest.raises(RenderError, match="indica"):
        render_project_clips("proyecto", options=RenderOptions(), settings=settings)


def _project(tmp_path: Path, settings: Settings) -> tuple[str, Path]:
    """Proyecto mínimo con fuente real, transcripción y candidatos."""
    project_id = "proyecto"
    storage = LocalStorage(settings.storage_dir)
    storage.ensure_project_dirs(project_id)
    video = storage.source_dir(project_id) / "original.mp4"
    result = subprocess.run(
        [
            str(settings.ffmpeg_bin),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            "6",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"ffmpeg no disponible: {result.stderr[-200:]}")
    storage.write_json_atomic(
        storage.selection_path(project_id),
        CandidatesDocument(
            project_id=project_id,
            requested=1,
            provider="test:model",
            candidates=[_candidate()],
        ),
    )
    from winclip.pipeline.schemas import Transcript

    storage.write_json_atomic(
        storage.transcript_path(project_id),
        Transcript(language="es", duration=6.0, model="test", segments=[]),
    )
    return project_id, video


def test_render_clip_cleans_up_on_error(
    ffmpeg_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, _ = _project(tmp_path, ffmpeg_settings)
    clips_dir = LocalStorage(ffmpeg_settings.storage_dir).project_dir(project_id) / "clips"

    def boom(*args, **kwargs):
        raise RenderError("fallo simulado en el reencuadre")

    monkeypatch.setattr(render_module, "compute_reframe", boom)

    with pytest.raises(RenderError, match="fallo simulado"):
        render_clip(project_id, "01jcand", RenderOptions(), settings=ffmpeg_settings)

    assert not clips_dir.exists() or not any(clips_dir.iterdir())


def test_render_clip_validates_inputs(ffmpeg_settings: Settings, tmp_path: Path) -> None:
    settings = ffmpeg_settings
    project_id, _ = _project(tmp_path, settings)
    storage = LocalStorage(settings.storage_dir)

    with pytest.raises(RenderError, match="no existe el candidato"):
        render_clip(project_id, "01jnoexiste", RenderOptions(), settings=settings)

    storage.selection_path(project_id).unlink()
    with pytest.raises(RenderError, match="winclip select"):
        render_clip(project_id, "01jcand", RenderOptions(), settings=settings)


def test_render_clip_rejects_missing_transcript(ffmpeg_settings: Settings, tmp_path: Path) -> None:
    project_id, _ = _project(tmp_path, ffmpeg_settings)
    storage = LocalStorage(ffmpeg_settings.storage_dir)
    storage.transcript_path(project_id).unlink()

    with pytest.raises(RenderError, match="winclip transcribe"):
        render_clip(project_id, "01jcand", RenderOptions(), settings=ffmpeg_settings)


def test_manifest_json_has_no_extra_fields(tmp_path: Path) -> None:
    clip_dir = tmp_path / "clips" / "01jclip"
    _write_manifest(clip_dir, "01jcand")
    payload = json.loads((clip_dir / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert len(payload) == 11
    assert "fingerprint" not in payload


def test_candidate_proposal_is_not_a_render_input() -> None:
    # El render consume `ClipCandidate` de `candidates.json`, no la propuesta del LLM.
    proposal = CandidateProposal(start=1.0, end=2.0, score=50)
    assert proposal.score == 50
