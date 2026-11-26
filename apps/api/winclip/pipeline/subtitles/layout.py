"""Re-temporización y agrupación karaoke compartida por los motores `ass` y `pil`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from winclip.pipeline.schemas import Transcript
from winclip.pipeline.subtitles.presets import SubtitlePreset

MIN_WORD_DURATION = 0.04
LAYOUT_WIDTH = 1080
SENTENCE_ENDINGS = (".", "?", "!", "…")
SOFT_BREAKS = (",", ";", ":")
_TRAILING = "\"'\u201d\u2019\u00bb)]}"


@dataclass(frozen=True)
class TimedWord:
    """Palabra ya relativa al inicio del clip."""

    text: str
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True)
class SubtitleCue:
    """Bloque de subtítulos con sus palabras y líneas (máximo dos)."""

    words: tuple[TimedWord, ...]
    lines: tuple[tuple[TimedWord, ...], ...]
    emoji: str | None = None
    index: int = 0

    @property
    def start(self) -> float:
        return self.words[0].start if self.words else 0.0

    @property
    def end(self) -> float:
        return self.words[-1].end if self.words else 0.0

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)


@dataclass(frozen=True)
class WordState:
    """Estado karaoke: palabra activa y su posición dentro del bloque."""

    cue_index: int
    line_index: int
    word_index: int
    word: TimedWord
    start: float
    end: float
    order: int = field(default=0)


def _ends_sentence(text: str) -> bool:
    return text.rstrip(_TRAILING).endswith(SENTENCE_ENDINGS)


def _ends_soft(text: str) -> bool:
    return text.rstrip(_TRAILING).endswith(SOFT_BREAKS)


def retime_words(
    transcript: Transcript,
    start: float,
    end: float,
    *,
    uppercase: bool = False,
) -> list[TimedWord]:
    """Filtra y re-temporiza las palabras que caen dentro de `[start, end]`."""
    words: list[TimedWord] = []
    previous_end = 0.0
    for segment in transcript.segments:
        for word in segment.words:
            text = word.w.strip()
            if not text:
                continue
            if word.e <= start or word.s >= end:
                continue
            clipped_start = max(0.0, word.s - start)
            clipped_end = min(end, word.e) - start
            clipped_start = max(clipped_start, previous_end)
            clipped_end = max(clipped_end, clipped_start + MIN_WORD_DURATION)
            if uppercase:
                text = text.upper()
            words.append(
                TimedWord(
                    text=text,
                    start=round(clipped_start, 3),
                    end=round(clipped_end, 3),
                )
            )
            previous_end = clipped_end
    return words


def _wrap_lines(
    words: list[TimedWord],
    *,
    max_chars: int,
    max_lines: int,
) -> list[list[TimedWord]]:
    """Reparte palabras en líneas por caracteres y cortes suaves de puntuación."""
    lines: list[list[TimedWord]] = []
    line: list[TimedWord] = []
    length = 0
    for word in words:
        needed = len(word.text) + (1 if line else 0)
        if line and length + needed > max_chars:
            lines.append(line)
            line = [word]
            length = len(word.text)
            continue
        line.append(word)
        length += needed
        if _ends_soft(word.text) and len(line) > 1:
            lines.append(line)
            line = []
            length = 0
    if line:
        lines.append(line)

    if len(lines) > max_lines:
        # Reequilibra en como máximo `max_lines` líneas repartiendo por palabras.
        target = min(len(words), max(1, -(-len(words) // max_lines)))
        lines = []
        for index in range(0, len(words), target):
            lines.append(list(words[index : index + target]))
            if len(lines) == max_lines:
                lines[-1].extend(words[index + target :])
                break
    return lines


def _take_prefix(words: list[TimedWord], *, max_chars: int, max_lines: int) -> int:
    """Cuántas palabras caben en un bloque de `max_lines` líneas."""
    line_length = 0
    line_number = 1
    taken = 0
    for word in words:
        needed = len(word.text) + (1 if line_length else 0)
        if line_length and line_length + needed > max_chars:
            line_number += 1
            if line_number > max_lines:
                break
            line_length = len(word.text)
            taken += 1
            continue
        line_length += needed
        taken += 1
    return max(1, taken)


def _fit_prefix_pixels(
    words: list[TimedWord],
    measure: Callable[[str], float],
    *,
    max_width: float,
    max_lines: int,
) -> int:
    """Cuántas palabras caben en `max_lines` líneas medidas en píxeles."""
    lines = 1
    length = 0.0
    taken = 0
    for word in words:
        addition = measure(word.text) + (measure(" ") if length else 0.0)
        if length and length + addition > max_width:
            lines += 1
            if lines > max_lines:
                break
            length = measure(word.text)
            taken += 1
            continue
        length += addition
        taken += 1
    return max(1, taken)


def _wrap_pixels(
    words: list[TimedWord],
    measure: Callable[[str], float],
    *,
    max_width: float,
) -> list[list[TimedWord]]:
    """Reparte palabras en líneas que quepan en `max_width` píxeles."""
    lines: list[list[TimedWord]] = []
    line: list[TimedWord] = []
    length = 0.0
    for word in words:
        addition = measure(word.text) + (measure(" ") if line else 0.0)
        if line and length + addition > max_width:
            lines.append(line)
            line = [word]
            length = measure(word.text)
            continue
        line.append(word)
        length += addition
    if line:
        lines.append(line)
    return lines


def build_cues(
    words: list[TimedWord],
    preset: SubtitlePreset,
    *,
    measure: Callable[[str], float] | None = None,
) -> list[SubtitleCue]:
    """Agrupa palabras en bloques de 1-2 líneas respetando pausas y puntuación."""
    if not words:
        return []
    max_width = LAYOUT_WIDTH - 2 * preset.margin_x

    phrases: list[list[TimedWord]] = []
    current: list[TimedWord] = []
    for index, word in enumerate(words):
        current.append(word)
        following = words[index + 1] if index + 1 < len(words) else None
        boundary = (
            following is None
            or _ends_sentence(word.text)
            or (following.start - word.end) > preset.max_pause_sec
            or len(current) >= preset.max_words_per_cue
        )
        if boundary:
            phrases.append(current)
            current = []

    cues: list[SubtitleCue] = []
    for phrase in phrases:
        remaining = list(phrase)
        while remaining:
            if measure is None:
                size = _take_prefix(
                    remaining,
                    max_chars=preset.max_chars_per_line,
                    max_lines=preset.max_lines,
                )
                chunk = remaining[:size]
                remaining = remaining[size:]
                lines = _wrap_lines(
                    chunk,
                    max_chars=preset.max_chars_per_line,
                    max_lines=preset.max_lines,
                )
            else:
                size = _fit_prefix_pixels(
                    remaining,
                    measure,
                    max_width=max_width,
                    max_lines=preset.max_lines,
                )
                chunk = remaining[:size]
                remaining = remaining[size:]
                lines = _wrap_pixels(chunk, measure, max_width=max_width)
            cues.append(
                SubtitleCue(
                    words=tuple(chunk),
                    lines=tuple(tuple(line) for line in lines),
                    index=len(cues),
                )
            )
    return cues


def cue_scale(
    cue: SubtitleCue,
    measure: Callable[[str], float],
    max_width: float,
) -> float:
    """Factor de reducción (`<= 1`) para que la línea más ancha quepa en el ancho."""
    widest = max(
        (measure(" ".join(word.text for word in line)) for line in cue.lines),
        default=0.0,
    )
    if widest <= 0 or max_width <= 0:
        return 1.0
    return round(min(1.0, max_width / widest), 3)


def cue_states(cue: SubtitleCue) -> list[WordState]:
    """Estados karaoke del bloque: una entrada por palabra activa."""
    states: list[WordState] = []
    ordered = [
        (line_index, word_index, word)
        for line_index, line in enumerate(cue.lines)
        for word_index, word in enumerate(line)
    ]
    for order, (line_index, word_index, word) in enumerate(ordered):
        following = ordered[order + 1][2] if order + 1 < len(ordered) else None
        states.append(
            WordState(
                cue_index=cue.index,
                line_index=line_index,
                word_index=word_index,
                word=word,
                start=word.start,
                end=following.start if following is not None else cue.end,
                order=order,
            )
        )
    return states


def all_states(cues: list[SubtitleCue]) -> list[WordState]:
    """Todos los estados karaoke en orden temporal."""
    return [state for cue in cues for state in cue_states(cue)]
