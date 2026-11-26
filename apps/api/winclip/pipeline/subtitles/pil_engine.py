"""Motor de subtítulos `pil`: capa RGBA por estado karaoke lista para `overlay`."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from winclip.pipeline.subtitles.fonts import measure_font
from winclip.pipeline.subtitles.layout import (
    SubtitleCue,
    WordState,
    all_states,
    cue_scale,
    cue_states,
)
from winclip.pipeline.subtitles.presets import SubtitlePreset

SAFE_BOTTOM_OFFSET = 0.04
LINE_HEIGHT_RATIO = 1.16
SHADOW_ALPHA = 200


def hex_to_rgba(value: str) -> tuple[int, int, int, int]:
    """`#RRGGBB[AA]` → tupla RGBA."""
    cleaned = value.lstrip("#")
    red, green, blue = int(cleaned[0:2], 16), int(cleaned[2:4], 16), int(cleaned[4:6], 16)
    alpha = int(cleaned[6:8], 16) if len(cleaned) == 8 else 255
    return red, green, blue, alpha


class SubtitleFrameRenderer:
    """Renderiza un fotograma RGBA por estado de palabra con caché de un solo buffer."""

    def __init__(
        self,
        cues: list[SubtitleCue],
        preset: SubtitlePreset,
        font_path: Path,
        *,
        width: int = 1080,
        height: int = 1920,
    ) -> None:
        self.cues = cues
        self.preset = preset
        self.font_path = Path(font_path)
        self.width = width
        self.height = height
        self._by_cue = {cue.index: cue for cue in cues}
        self._states = {
            cue.index: {state.order: state for state in cue_states(cue)} for cue in cues
        }
        self._schedule = [
            (state.start, state.end, cue.index, state)
            for cue in cues
            for state in all_states([cue])
        ]
        self._fonts: dict[int, ImageFont.FreeTypeFont] = {}
        self._measure_fn = None
        self._cache_key: tuple[int, int] | None = None
        self._cache: np.ndarray | None = None

    # ------------------------------------------------------------------ fuentes
    def _font(self, size: int) -> ImageFont.FreeTypeFont:
        if size not in self._fonts:
            self._fonts[size] = ImageFont.truetype(str(self.font_path), size)
        return self._fonts[size]

    def _measure(self):
        """Medidor de anchos a tamaño base (cacheado por renderer)."""
        if self._measure_fn is None:
            self._measure_fn = measure_font(self.font_path, self.preset.font_size)
        return self._measure_fn

    def _sizes(self, cue: SubtitleCue) -> tuple[int, int]:
        """Tamaños `(base, activo)` reducidos si la línea más ancha no cabe."""
        scale = cue_scale(cue, self._measure(), self.width - 2 * self.preset.margin_x)
        base = max(12, round(self.preset.font_size * scale))
        active = max(12, round(base * self.preset.highlight_scale_pct / 100))
        return base, active

    # ------------------------------------------------------------------ render
    def _block_bottom(self) -> int:
        bottom = min(0.70, self.preset.y_pct + SAFE_BOTTOM_OFFSET)
        return round(bottom * self.height)

    def render_state(self, cue_index: int, order: int) -> np.ndarray:
        """Imagen RGBA `widthxheight` con el bloque y la palabra activa resaltada."""
        if self._cache_key == (cue_index, order) and self._cache is not None:
            return self._cache

        image = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        cue = self._by_cue[cue_index]
        state = self._states[cue_index][order]
        base_size, active_size = self._sizes(cue)
        base_font = self._font(base_size)
        highlight_font = self._font(active_size)
        line_height = round(base_size * LINE_HEIGHT_RATIO)
        space = round(base_size * 0.28)

        measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        lines = [list(line) for line in cue.lines]
        widths: list[list[int]] = []
        for line_index, line in enumerate(lines):
            widths.append(
                [
                    int(measure.textlength(word.text, font=base_font))
                    if not self._is_active(state, line_index, word_index)
                    else int(measure.textlength(word.text, font=highlight_font))
                    for word_index, word in enumerate(line)
                ]
            )

        bottom = self._block_bottom()
        if self.preset.box_bg_color:
            block_height = line_height * len(lines)
            inner_width = max(
                (
                    sum(widths[index]) + space * (len(lines[index]) - 1)
                    for index in range(len(lines))
                ),
                default=0,
            )
            box_left = max(0, (self.width - inner_width) // 2 - 32)
            box_right = min(self.width, (self.width + inner_width) // 2 + 32)
            draw.rounded_rectangle(
                (box_left, bottom - block_height - 16, box_right, bottom + 16),
                radius=28,
                fill=hex_to_rgba(self.preset.box_bg_color),
            )

        for line_index, line in enumerate(lines):
            y = bottom - (len(lines) - line_index) * line_height
            total = sum(widths[line_index]) + space * (len(line) - 1)
            x = max(self.preset.margin_x, (self.width - total) // 2)
            for word_index, word in enumerate(line):
                if self._is_active(state, line_index, word_index):
                    center = x + widths[line_index][word_index] // 2
                    self._draw_word(
                        draw,
                        word.text,
                        highlight_font,
                        (center, y),
                        anchor="mt",
                        fill=self.preset.highlight_color,
                    )
                else:
                    self._draw_word(
                        draw,
                        word.text,
                        base_font,
                        (x, y),
                        anchor="lt",
                        fill=self.preset.primary_color,
                    )
                x += widths[line_index][word_index] + space

        array = np.asarray(image, dtype=np.uint8)
        self._cache_key = (cue_index, order)
        self._cache = array
        return array

    def _is_active(self, state: WordState, line_index: int, word_index: int) -> bool:
        return line_index == state.line_index and word_index == state.word_index

    def _draw_word(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        position: tuple[int, int],
        *,
        anchor: str,
        fill: str,
    ) -> None:
        depth = self.preset.shadow_depth
        if depth:
            draw.text(
                (position[0] + depth, position[1] + depth),
                text,
                font=font,
                fill=(0, 0, 0, SHADOW_ALPHA),
                anchor=anchor,
            )
        draw.text(
            position,
            text,
            font=font,
            fill=hex_to_rgba(fill),
            anchor=anchor,
            stroke_width=self.preset.outline_width,
            stroke_fill=hex_to_rgba(self.preset.outline_color),
        )

    def empty_frame(self) -> np.ndarray:
        """Fotograma totalmente transparente (sin palabra activa)."""
        return np.zeros((self.height, self.width, 4), dtype=np.uint8)

    def frame_at(self, moment: float) -> np.ndarray:
        """Fotograma RGBA del instante `moment` (segundos relativos al clip)."""
        active: tuple[int, WordState] | None = None
        for start, end, cue_index, state in self._schedule:
            if start <= moment < end:
                active = (cue_index, state)
            elif start > moment:
                break
        if active is None:
            return self.empty_frame()
        cue_index, state = active
        return self.render_state(cue_index, state.order)

    def iter_frames(self, duration: float, fps: float) -> Iterator[np.ndarray]:
        """Un fotograma RGBA por frame de video, reutilizando el buffer del estado."""
        total = max(1, round(duration * fps))
        for index in range(total):
            yield self.frame_at(index / fps)
