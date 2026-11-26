"""Tests del pipeline de ingesta (URL con yt-dlp falso, archivo local real)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

import pytest
import yt_dlp

from winclip.core.config import Settings
from winclip.core.storage import LocalStorage
from winclip.pipeline import ingest as ingest_module
from winclip.pipeline.ingest import (
    DownloadedMedia,
    IngestError,
    InvalidUrlError,
    LiveStreamNotSupportedError,
    MissingAudioError,
    PrivateVideoError,
    ProjectExistsError,
    YtDlpDownloader,
    ingest,
)
from winclip.pipeline.schemas import SourceMeta


def _audio_stream(settings: Settings, path: Path) -> dict[str, object]:
    proc = subprocess.run(
        [
            str(settings.ffprobe_bin),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    streams = json.loads(proc.stdout)["streams"]
    return next(stream for stream in streams if stream["codec_type"] == "audio")


def test_ingest_local_file_copies_and_extracts(
    ffmpeg_settings: Settings, synthetic_video: Path
) -> None:
    storage = LocalStorage(ffmpeg_settings.storage_dir)

    result = ingest(str(synthetic_video), settings=ffmpeg_settings, project_id="proyecto01")

    meta = SourceMeta.model_validate(storage.read_json(storage.source_meta_path("proyecto01")))
    assert result.project_id == "proyecto01"
    assert meta.project_id == "proyecto01"
    assert meta.source_type == "file"
    assert meta.source_url is None
    assert meta.title == "sample"
    assert meta.channel is None
    assert meta.uploader_id is None
    assert meta.has_audio is True
    assert (meta.width, meta.height) == (320, 240)
    assert meta.video_codec == "h264"
    assert meta.audio_codec == "aac"
    assert 1.5 <= meta.duration <= 2.5
    assert meta.fps == pytest.approx(30.0, abs=0.1)
    assert meta.file_size_bytes == result.video_path.stat().st_size

    # El archivo original queda intacto y la copia conserva los bytes.
    assert synthetic_video.exists()
    assert result.video_path.read_bytes() == synthetic_video.read_bytes()
    assert result.video_path.name == "original.mp4"

    audio = _audio_stream(ffmpeg_settings, result.audio_path)
    assert int(audio["sample_rate"]) == 16000
    assert audio["channels"] == 1
    assert audio["codec_name"] == "pcm_s16le"


def test_ingest_reports_monotonic_progress(
    ffmpeg_settings: Settings, synthetic_video: Path
) -> None:
    events: list[tuple[float, str]] = []

    ingest(
        str(synthetic_video),
        settings=ffmpeg_settings,
        project_id="progreso",
        progress=lambda value, stage: events.append((value, stage)),
    )

    values = [value for value, _ in events]
    assert values == sorted(values)
    assert values[0] == 0.0
    assert values[-1] == 100.0
    assert {"copy", "probe", "extract_audio"} <= {stage for _, stage in events}


def test_ingest_missing_audio_fails_without_meta(
    ffmpeg_settings: Settings, silent_video: Path
) -> None:
    storage = LocalStorage(ffmpeg_settings.storage_dir)

    with pytest.raises(MissingAudioError, match="no contiene audio"):
        ingest(str(silent_video), settings=ffmpeg_settings, project_id="sin-audio")

    assert not storage.source_meta_path("sin-audio").exists()


def test_ingest_rejects_unsupported_extension(sample_settings: Settings, tmp_path: Path) -> None:
    note = tmp_path / "nota.txt"
    note.write_text("hola", encoding="utf-8")

    with pytest.raises(IngestError, match="extensión no soportada"):
        ingest(str(note), settings=sample_settings)


def test_ingest_rejects_missing_file(sample_settings: Settings, tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="no existe"):
        ingest(str(tmp_path / "no-existe.mp4"), settings=sample_settings)


def test_ingest_refuses_overwrite_without_force(
    ffmpeg_settings: Settings, synthetic_video: Path
) -> None:
    ingest(str(synthetic_video), settings=ffmpeg_settings, project_id="dup")

    with pytest.raises(ProjectExistsError, match="--force"):
        ingest(str(synthetic_video), settings=ffmpeg_settings, project_id="dup")

    forced = ingest(str(synthetic_video), settings=ffmpeg_settings, project_id="dup", force=True)
    assert forced.project_id == "dup"


class _CopyingDownloader:
    """Descargador falso que copia un video local, para probar el flujo URL."""

    def __init__(self, video: Path) -> None:
        self.video = video
        self.calls: list[str] = []

    def download(
        self,
        url: str,
        destination: Path,
        on_progress: object = None,
    ) -> DownloadedMedia:
        self.calls.append(url)
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / "original.mp4"
        shutil.copyfile(self.video, path)
        if callable(on_progress):
            on_progress(40.0)
            on_progress(100.0)
        return DownloadedMedia(
            path=path,
            title="Video remoto",
            channel="HookVault",
            uploader_id="@hookvault",
            duration=2.0,
        )


def test_ingest_url_uses_downloader_and_records_metadata(
    ffmpeg_settings: Settings, synthetic_video: Path
) -> None:
    storage = LocalStorage(ffmpeg_settings.storage_dir)
    downloader = _CopyingDownloader(synthetic_video)
    events: list[tuple[float, str]] = []

    result = ingest(
        "https://www.youtube.com/watch?v=abc",
        settings=ffmpeg_settings,
        project_id="remoto",
        downloader=downloader,
        progress=lambda value, stage: events.append((value, stage)),
    )

    meta = SourceMeta.model_validate(storage.read_json(storage.source_meta_path("remoto")))
    assert downloader.calls == ["https://www.youtube.com/watch?v=abc"]
    assert meta.source_type == "url"
    assert meta.source_url == "https://www.youtube.com/watch?v=abc"
    assert meta.title == "Video remoto"
    assert meta.channel == "HookVault"
    assert meta.uploader_id == "@hookvault"
    assert result.video_path.name == "original.mp4"
    assert "download" in {stage for _, stage in events}


class _FakeYDL:
    """Doble de `yt_dlp.YoutubeDL` controlable por atributos de clase."""

    info: ClassVar[dict[str, object]] = {}
    error: ClassVar[Exception | None] = None
    download_called: ClassVar[bool] = False
    last_options: ClassVar[dict[str, object]] = {}

    def __init__(self, options: dict[str, object]) -> None:
        _FakeYDL.last_options = options
        self.options = options

    def __enter__(self) -> _FakeYDL:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def extract_info(self, _url: str, download: bool = False) -> dict[str, object]:
        if _FakeYDL.error is not None:
            raise _FakeYDL.error
        return dict(_FakeYDL.info)

    def download(self, _urls: list[str]) -> None:
        _FakeYDL.download_called = True
        if _FakeYDL.error is not None:
            raise _FakeYDL.error
        target = Path(str(self.options["outtmpl"]).replace("%(ext)s", "mp4"))
        hook = self.options["progress_hooks"][0]  # type: ignore[index]
        hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
        target.write_bytes(b"fake-mp4")
        hook({"status": "finished"})


@pytest.fixture
def fake_ytdlp(monkeypatch: pytest.MonkeyPatch) -> type[_FakeYDL]:
    _FakeYDL.info = {}
    _FakeYDL.error = None
    _FakeYDL.download_called = False
    _FakeYDL.last_options = {}
    monkeypatch.setattr(ingest_module.yt_dlp, "YoutubeDL", _FakeYDL)
    return _FakeYDL


def test_ytdlp_download_builds_expected_options(
    fake_ytdlp: type[_FakeYDL], sample_settings: Settings, tmp_path: Path
) -> None:
    fake_ytdlp.info = {
        "is_live": False,
        "title": "Título del video",
        "channel": "HookVault",
        "uploader_id": "@hookvault",
        "duration": 612.4,
    }
    events: list[float] = []

    media = YtDlpDownloader(sample_settings).download(
        "https://www.youtube.com/watch?v=abc", tmp_path, on_progress=events.append
    )

    assert media.path == tmp_path / "original.mp4"
    assert media.path.read_bytes() == b"fake-mp4"
    assert (media.title, media.channel, media.uploader_id) == (
        "Título del video",
        "HookVault",
        "@hookvault",
    )
    assert media.duration == 612.4
    options = fake_ytdlp.last_options
    assert "height<=1080" in str(options["format"])
    assert options["merge_output_format"] == "mp4"
    assert options["ffmpeg_location"] == str(sample_settings.ffmpeg_bin)
    assert options["noplaylist"] is True
    assert events == [50.0]


def test_ytdlp_rejects_invalid_url(
    fake_ytdlp: type[_FakeYDL], sample_settings: Settings, tmp_path: Path
) -> None:
    fake_ytdlp.error = yt_dlp.utils.DownloadError(
        "ERROR: Unsupported URL: https://ejemplo.invalido/no-video"
    )

    with pytest.raises(InvalidUrlError):
        YtDlpDownloader(sample_settings).download("https://ejemplo.invalido/no-video", tmp_path)

    with pytest.raises(InvalidUrlError):
        YtDlpDownloader(sample_settings).download("no-es-una-url", tmp_path)


def test_ytdlp_rejects_private_video(
    fake_ytdlp: type[_FakeYDL], sample_settings: Settings, tmp_path: Path
) -> None:
    fake_ytdlp.error = yt_dlp.utils.DownloadError(
        "ERROR: [youtube] abc: Private video. Sign in if you've been granted access"
    )

    with pytest.raises(PrivateVideoError, match="privado"):
        YtDlpDownloader(sample_settings).download("https://youtu.be/abc", tmp_path)


def test_ytdlp_rejects_live_stream_before_downloading(
    fake_ytdlp: type[_FakeYDL], sample_settings: Settings, tmp_path: Path
) -> None:
    fake_ytdlp.info = {"is_live": True, "title": "Directo"}

    with pytest.raises(LiveStreamNotSupportedError, match="directo"):
        YtDlpDownloader(sample_settings).download("https://youtu.be/live", tmp_path)

    assert fake_ytdlp.download_called is False


def test_ytdlp_maps_other_errors_to_ingest_error(
    fake_ytdlp: type[_FakeYDL], sample_settings: Settings, tmp_path: Path
) -> None:
    fake_ytdlp.error = yt_dlp.utils.DownloadError("ERROR: HTTP Error 500: Internal Server Error")

    with pytest.raises(IngestError) as excinfo:
        YtDlpDownloader(sample_settings).download("https://youtu.be/abc", tmp_path)

    assert not isinstance(excinfo.value, (InvalidUrlError, PrivateVideoError))
