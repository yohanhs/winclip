"""Tests de integración lentos: transcripción real con `mlx-whisper`."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from winclip.core.config import Settings
from winclip.core.storage import LocalStorage
from winclip.pipeline.schemas import Transcript
from winclip.pipeline.transcribe import MlxWhisperBackend, transcribe

pytestmark = pytest.mark.slow

MODEL_ALIAS = "tiny"


def _require_mlx() -> None:
    if sys.platform != "darwin" or platform.machine() != "arm64":
        pytest.skip("mlx-whisper solo está disponible en macOS arm64")
    pytest.importorskip("mlx_whisper")


def _speech_wav(tmp_path: Path, settings: Settings) -> Path:
    """Audio corto: voz sintetizada con `say` si existe, si no un tono de 2 s."""
    wav = tmp_path / "speech.wav"
    say = shutil.which("say")
    command = [str(settings.ffmpeg_bin), "-y"]
    if say is not None:
        aiff = tmp_path / "speech.aiff"
        subprocess.run(
            [say, "-o", str(aiff), "Hola, esto es una prueba de WinClip."],
            check=True,
            capture_output=True,
        )
        command += ["-i", str(aiff)]
    else:
        command += ["-f", "lavfi", "-i", "sine=frequency=440:duration=2"]
    command += ["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)]
    subprocess.run(command, check=True, capture_output=True)
    return wav


def test_transcribe_with_mlx_whisper_tiny(tmp_path: Path, ffmpeg_settings: Settings) -> None:
    _require_mlx()
    storage = LocalStorage(ffmpeg_settings.storage_dir)
    project_id = "slowtest"
    storage.ensure_project_dirs(project_id)
    shutil.copyfile(_speech_wav(tmp_path, ffmpeg_settings), storage.audio_path(project_id))

    events: list[tuple[float, str]] = []
    result = transcribe(
        project_id,
        settings=ffmpeg_settings,
        storage=storage,
        model=MODEL_ALIAS,
        language="es",
        backend=MlxWhisperBackend(),
        progress=lambda value, stage: events.append((value, stage)),
    )

    transcript = Transcript.model_validate(storage.read_json(result.path))

    assert transcript.model == "mlx-community/whisper-tiny"
    assert transcript.language == "es"
    assert transcript.duration >= 0
    for segment in transcript.segments:
        assert segment.end >= segment.start
        for word in segment.words:
            assert word.w
            assert 0 <= word.s <= word.e
            assert 0 <= word.p <= 1
    assert events[-1][0] == 100.0
