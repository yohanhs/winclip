"""Subtítulos karaoke: presets, fuentes, agrupación y motores `ass` y `pil`."""

from __future__ import annotations

from winclip.pipeline.subtitles.ass_engine import build_ass, write_ass
from winclip.pipeline.subtitles.fonts import (
    FontFile,
    FontsLookup,
    ResolvedFont,
    fonts_directory,
    resolve_font,
)
from winclip.pipeline.subtitles.layout import (
    SubtitleCue,
    TimedWord,
    WordState,
    build_cues,
    cue_states,
    retime_words,
)
from winclip.pipeline.subtitles.pil_engine import SubtitleFrameRenderer
from winclip.pipeline.subtitles.presets import (
    SubtitlePreset,
    SubtitlePresetError,
    list_presets,
    load_preset,
)

__all__ = [
    "FontFile",
    "FontsLookup",
    "ResolvedFont",
    "SubtitleCue",
    "SubtitleFrameRenderer",
    "SubtitlePreset",
    "SubtitlePresetError",
    "TimedWord",
    "WordState",
    "build_ass",
    "build_cues",
    "cue_states",
    "fonts_directory",
    "list_presets",
    "load_preset",
    "resolve_font",
    "retime_words",
    "write_ass",
]
