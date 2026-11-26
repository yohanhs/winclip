"""Test de integración `@slow`: render real con ambos motores y benchmark en M1."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from pathlib import Path

import pytest

from winclip.core.config import Settings
from winclip.core.storage import LocalStorage
from winclip.pipeline.reframe import ReframeError, ensure_yunet_model
from winclip.pipeline.render import render_clip
from winclip.pipeline.render_models import (
    MANIFEST_FILENAME,
    RenderManifest,
    RenderOptions,
    RenderProgress,
)
from winclip.pipeline.schemas import Transcript, TranscriptSegment, WordTimestamp
from winclip.pipeline.select import CandidatesDocument, ClipCandidate

pytestmark = pytest.mark.slow

CANDIDATE_ID = "cand01"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        storage_dir=tmp_path / "storage",
        user_fonts_dir=tmp_path / "fuentes",
    )


def _make_source(path: Path, settings: Settings, *, width: int, height: int, seconds: int) -> Path:
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
            f"testsrc2=size={width}x{height}:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            str(seconds),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"ffmpeg no disponible: {result.stderr[-200:]}")
    return path


def _project(tmp_path: Path, settings: Settings, *, seconds: int = 4, width: int = 1920) -> str:
    project_id = "integracion"
    storage = LocalStorage(settings.storage_dir)
    storage.ensure_project_dirs(project_id)
    _make_source(
        storage.source_dir(project_id) / "original.mp4",
        settings,
        width=width,
        height=width * 9 // 16,
        seconds=seconds,
    )

    words: list[WordTimestamp] = []
    moment = 0.2
    for text in [
        "este",
        "es",
        "un",
        "clip",
        "de",
        "prueba",
        "con",
        "subtitulos",
        "karaoke",
        "verticales",
        "y",
        "hook",
    ]:
        words.append(WordTimestamp(w=text, s=round(moment, 3), e=round(moment + 0.3, 3), p=0.95))
        moment += 0.35
    storage.write_json_atomic(
        storage.transcript_path(project_id),
        Transcript(
            language="es",
            duration=float(seconds),
            model="test",
            segments=[
                TranscriptSegment(
                    id=0,
                    start=0.0,
                    end=float(seconds),
                    text=" ".join(word.w for word in words),
                    words=words,
                )
            ],
        ),
    )
    storage.write_json_atomic(
        storage.selection_path(project_id),
        CandidatesDocument(
            project_id=project_id,
            requested=1,
            provider="test:model",
            candidates=[
                ClipCandidate(
                    id=CANDIDATE_ID,
                    start=0.2,
                    end=float(seconds) - 0.2,
                    title="Clip de prueba",
                    hook="Mira esto",
                    description="demo",
                    hashtags=["#demo"],
                    score=95,
                    reason="test",
                    language="es",
                )
            ],
        ),
    )
    return project_id


def _probe(path: Path, settings: Settings) -> dict:
    result = subprocess.run(
        [
            str(settings.ffprobe_bin),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _assert_clip(clip_dir: Path, settings: Settings) -> RenderManifest:
    manifest = RenderManifest.model_validate_json(
        (clip_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    probe = _probe(clip_dir / manifest.output, settings)
    video = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
    audio = next(stream for stream in probe["streams"] if stream["codec_type"] == "audio")

    assert video["codec_name"] == "h264"
    assert (video["width"], video["height"]) == (1080, 1920)
    numerator, denominator = video["avg_frame_rate"].split("/")
    assert float(numerator) / float(denominator) <= 30.5
    assert audio["codec_name"] == "aac"
    assert (clip_dir / manifest.thumbnail).is_file()
    assert (clip_dir / "subs.ass").stat().st_size > 0

    thumbnail = _probe(clip_dir / manifest.thumbnail, settings)["streams"][0]
    assert (thumbnail["width"], thumbnail["height"]) == (1080, 1920)
    assert set(manifest.model_dump()) == {
        "clip_id",
        "candidate_id",
        "width",
        "height",
        "fps",
        "reframe",
        "subtitles",
        "hook_overlay",
        "duration",
        "output",
        "thumbnail",
    }
    return manifest


@pytest.mark.parametrize("engine", ["ass", "pil"])
@pytest.mark.parametrize("mode", ["center", "blur", "face"])
def test_render_modes_and_engines(tmp_path: Path, engine: str, mode: str) -> None:
    settings = _settings(tmp_path)
    if mode == "face":
        try:
            ensure_yunet_model(settings)
        except ReframeError as exc:
            pytest.skip(f"modelo YuNet no disponible sin red: {exc}")
    project_id = _project(tmp_path, settings)
    progress: list[RenderProgress] = []

    manifest = render_clip(
        project_id,
        CANDIDATE_ID,
        RenderOptions(reframe=mode, engine=engine),
        settings=settings,
        on_progress=progress.append,
    )

    clip_dir = (
        LocalStorage(settings.storage_dir).project_dir(project_id) / "clips" / manifest.clip_id
    )
    _assert_clip(clip_dir, settings)
    assert manifest.subtitles.engine == engine
    assert manifest.hook_overlay is True
    if mode == "face":
        assert manifest.reframe.mode in {"face", "passthrough"}

    percents = [item.percent for item in progress]
    assert percents == sorted(percents), "el progreso debe ser monotónico"
    assert percents[0] <= 5
    assert percents[-1] == 100.0
    assert {item.stage for item in progress} >= {"reframe", "subtitles", "encode", "thumbnail"}


def test_render_is_idempotent_and_force_rerenders(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    project_id = _project(tmp_path, settings)
    clip_dir = LocalStorage(settings.storage_dir).project_dir(project_id) / "clips"

    first = render_clip(
        project_id, CANDIDATE_ID, RenderOptions(reframe="center"), settings=settings
    )
    video = clip_dir / first.clip_id / first.output
    first_mtime = video.stat().st_mtime_ns

    second = render_clip(
        project_id, CANDIDATE_ID, RenderOptions(reframe="center"), settings=settings
    )
    assert second.clip_id == first.clip_id
    assert video.stat().st_mtime_ns == first_mtime

    time.sleep(0.01)
    forced = render_clip(
        project_id,
        CANDIDATE_ID,
        RenderOptions(reframe="center", force=True),
        settings=settings,
    )
    assert forced.clip_id == first.clip_id
    assert video.stat().st_mtime_ns != first_mtime
    assert len(list(clip_dir.iterdir())) == 1


def test_render_benchmark_m1_60s(tmp_path: Path) -> None:
    """60 s de clip 1080p con face+ass+VideoToolbox en menos de 60 s (M1)."""
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        pytest.skip("benchmark objetivo solo en Apple Silicon")
    settings = _settings(tmp_path)
    if not os.path.exists(settings.ffmpeg_bin):
        pytest.skip("ffmpeg-full no disponible")
    try:
        ensure_yunet_model(settings)
    except ReframeError as exc:
        pytest.skip(f"modelo YuNet no disponible sin red: {exc}")

    project_id = _project(tmp_path, settings, seconds=60, width=1920)
    progress: list[RenderProgress] = []

    started = time.perf_counter()
    manifest = render_clip(
        project_id,
        CANDIDATE_ID,
        RenderOptions(reframe="face", engine="ass"),
        settings=settings,
        on_progress=progress.append,
    )
    elapsed = time.perf_counter() - started

    clip_dir = (
        LocalStorage(settings.storage_dir).project_dir(project_id) / "clips" / manifest.clip_id
    )
    _assert_clip(clip_dir, settings)
    print(
        f"\nbenchmark render 60 s 1080p: {elapsed:.1f} s "
        f"({manifest.duration:.1f} s de clip, modo {manifest.reframe.mode})"
    )
    assert manifest.duration > 55
    assert elapsed < 60.0, f"render demasiado lento: {elapsed:.1f} s"
