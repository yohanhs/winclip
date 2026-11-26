"""`/api/presets`: catálogo de presets de subtítulos del change 3."""

from __future__ import annotations

from fastapi import APIRouter

from winclip.pipeline.subtitles.presets import list_presets, load_preset, presets_dir
from winclip.routers.schemas import SubtitlePresetOut

router = APIRouter(prefix="/api/presets", tags=["presets"])


@router.get("", response_model=list[SubtitlePresetOut], operation_id="listSubtitlePresets")
def list_subtitle_presets() -> list[SubtitlePresetOut]:
    """Presets disponibles leídos de `assets/subtitle-presets/*.json`."""
    return [
        SubtitlePresetOut.from_preset(name, load_preset(name, directory=presets_dir()))
        for name in list_presets()
    ]
