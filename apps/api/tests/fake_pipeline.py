"""Pipeline falso y determinista para los tests del worker."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from winclip.core.ids import new_ulid
from winclip.core.storage import LocalStorage
from winclip.pipeline.render_models import (
    ReframeSpec,
    RenderManifest,
    RenderProgress,
    SubtitleSummary,
)
from winclip.pipeline.schemas import SourceMeta
from winclip.pipeline.select import CandidatesDocument, ClipCandidate
from winclip.worker.handlers import PipelineBackends


def candidates(project_id: str, count: int = 2) -> list[ClipCandidate]:
    return [
        ClipCandidate(
            id=f"cand-{project_id}-{index}",
            start=float(index * 60),
            end=float(index * 60 + 30),
            title=f"Clip {index + 1}",
            hook=f"Gancho {index + 1}",
            description=f"Descripción {index + 1}",
            hashtags=["#shorts"],
            score=90 - index,
            reason="fake",
            language="es",
        )
        for index in range(count)
    ]


def write_candidates(
    storage: LocalStorage,
    project_id: str,
    count: int = 2,
) -> list[ClipCandidate]:
    document = CandidatesDocument(
        project_id=project_id,
        requested=count,
        provider="fake:model",
        candidates=candidates(project_id, count),
    )
    storage.write_json_atomic(storage.selection_path(project_id), document)
    return document.candidates


@dataclass
class FakePipeline:
    """Backends inyectables que no tocan ffmpeg, MLX ni la red."""

    storage: LocalStorage
    candidate_count: int = 2
    calls: list[str] = field(default_factory=list)
    after_transcribe: Callable[[], None] | None = None
    fail_transcribe: bool = False
    render_duration: float = 30.0

    def backends(self) -> PipelineBackends:
        return PipelineBackends(
            ingest=self.ingest,
            transcribe=self.transcribe,
            select=self.select,
            render=self.render,
            poll_seconds=0.01,
        )

    # ------------------------------------------------------------------ fases

    def ingest(self, url: str, *, settings, project_id: str, force: bool, progress) -> Any:
        self.calls.append("ingest")
        storage = LocalStorage(settings.storage_dir)
        storage.ensure_project_dirs(project_id)
        video = storage.source_dir(project_id) / "original.mp4"
        video.write_bytes(b"fake-mp4")
        meta = SourceMeta(
            project_id=project_id,
            source_type="url",
            source_url=url,
            original_filename="original.mp4",
            title="Demo",
            duration=600.0,
            width=1920,
            height=1080,
            fps=30.0,
            video_codec="h264",
            audio_codec="aac",
            audio_sample_rate=48000,
            has_audio=True,
            file_size_bytes=video.stat().st_size,
        )
        storage.write_json_atomic(storage.source_meta_path(project_id), meta)
        if progress is not None:
            progress(100.0, "download")
        return SimpleNamespace(meta=meta, video_path=video)

    def transcribe(self, project_id: str, *, settings, language: str, progress) -> Any:
        self.calls.append("transcribe")
        if progress is not None:
            progress(50.0, "load_model")
            progress(100.0, "transcribe")
        if self.after_transcribe is not None:
            self.after_transcribe()
        if self.fail_transcribe:
            raise RuntimeError("fallo simulado de transcripción")
        return SimpleNamespace(project_id=project_id, reused=False)

    def select(self, project_id: str, *, settings, count: int | str) -> Any:
        self.calls.append("select")
        storage = LocalStorage(settings.storage_dir)
        document = CandidatesDocument(
            project_id=project_id,
            requested=count,
            provider="fake:model",
            candidates=candidates(project_id, self.candidate_count),
        )
        storage.write_json_atomic(storage.selection_path(project_id), document)
        return SimpleNamespace(document=document)

    def render(
        self,
        project_id: str,
        candidate_id: str,
        options,
        *,
        settings,
        on_progress,
        clip_id: str | None = None,
    ) -> Any:
        self.calls.append(f"render:{candidate_id}")
        storage = LocalStorage(settings.storage_dir)
        clip_id = clip_id or new_ulid()
        target = storage.clip_dir(project_id, clip_id)
        target.mkdir(parents=True, exist_ok=True)
        (target / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"0" * 2048)
        (target / "thumb.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"1" * 128)
        if on_progress is not None:
            on_progress(
                RenderProgress(
                    clip_id=clip_id,
                    candidate_id=candidate_id,
                    stage="encode",
                    percent=50.0,
                    message="mitad",
                )
            )
            on_progress(
                RenderProgress(
                    clip_id=clip_id,
                    candidate_id=candidate_id,
                    stage="thumbnail",
                    percent=100.0,
                    message="listo",
                )
            )
        return RenderManifest(
            clip_id=clip_id,
            candidate_id=candidate_id,
            width=1080,
            height=1920,
            fps=30,
            reframe=ReframeSpec(mode="face", track=[[0.0, 0.5]]),
            subtitles=SubtitleSummary(
                engine="ass", preset=options.preset, font="Montserrat ExtraBold"
            ),
            hook_overlay=True,
            duration=self.render_duration,
            output="clip.mp4",
            thumbnail="thumb.jpg",
        )


def clip_dir_has_media(path: Path) -> bool:
    return (path / "clip.mp4").is_file() and (path / "thumb.jpg").is_file()
