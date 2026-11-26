"""Segmentación de transcripciones en utterances y *snap* a límites de palabra.

Las utterances agrupan palabras hasta puntuación terminal, una pausa natural o un tope
de palabras. El LLM solo ve esas frases compactas; después `snap_to_words` ajusta los
cortes a marcas temporales reales de `transcript.json` (`docs/architecture.md §6.1`).
"""

from __future__ import annotations

from dataclasses import dataclass

from winclip.pipeline.schemas import Transcript

DEFAULT_PAUSE_SECONDS = 0.7
DEFAULT_MAX_UTTERANCE_WORDS = 25
DEFAULT_SNAP_TOLERANCE_SECONDS = 3.0
DEFAULT_CHUNK_MAX_CHARS = 35_000
DEFAULT_CHUNK_OVERLAP_RATIO = 0.15

_SENTENCE_ENDINGS = (".", "?", "!", "…")
_TRAILING_CHARS = "\"'\u201d\u2019\u00bb)]}"


@dataclass(frozen=True)
class IndexedWord:
    """Palabra aplanada con su índice global y sus marcas temporales."""

    index: int
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class Utterance:
    """Frase candidata con el rango de palabras globales que la componen."""

    id: str
    start: float
    end: float
    text: str
    first_word: int
    last_word: int


@dataclass(frozen=True)
class TranscriptIndex:
    """Transcripción aplanada lista para serializar y ajustar cortes."""

    words: tuple[IndexedWord, ...]
    utterances: tuple[Utterance, ...]


def flatten_words(transcript: Transcript) -> list[IndexedWord]:
    """Aplana `segments[].words` conservando el orden y descartando vacíos."""
    words: list[IndexedWord] = []
    for segment in transcript.segments:
        for word in segment.words:
            text = word.w.strip()
            if not text:
                continue
            words.append(
                IndexedWord(
                    index=len(words),
                    text=text,
                    start=float(word.s),
                    end=float(word.e),
                )
            )
    return words


def _ends_sentence(text: str) -> bool:
    return text.rstrip(_TRAILING_CHARS).endswith(_SENTENCE_ENDINGS)


def _make_utterance(number: int, words: list[IndexedWord]) -> Utterance:
    return Utterance(
        id=f"U{number:04d}",
        start=words[0].start,
        end=words[-1].end,
        text=" ".join(word.text for word in words),
        first_word=words[0].index,
        last_word=words[-1].index,
    )


def build_utterances(
    words: list[IndexedWord],
    *,
    pause_seconds: float = DEFAULT_PAUSE_SECONDS,
    max_words: int = DEFAULT_MAX_UTTERANCE_WORDS,
) -> list[Utterance]:
    """Agrupa palabras por puntuación terminal, pausa >= `pause_seconds` o tope."""
    utterances: list[Utterance] = []
    current: list[IndexedWord] = []
    for position, word in enumerate(words):
        current.append(word)
        next_word = words[position + 1] if position + 1 < len(words) else None
        boundary = (
            next_word is None
            or len(current) >= max_words
            or _ends_sentence(word.text)
            or (next_word.start - word.end) >= pause_seconds
        )
        if boundary:
            utterances.append(_make_utterance(len(utterances) + 1, current))
            current = []
    return utterances


def build_index(
    transcript: Transcript,
    *,
    pause_seconds: float = DEFAULT_PAUSE_SECONDS,
    max_words: int = DEFAULT_MAX_UTTERANCE_WORDS,
) -> TranscriptIndex:
    """Aplana palabras y construye las utterances de una transcripción."""
    words = flatten_words(transcript)
    utterances = build_utterances(words, pause_seconds=pause_seconds, max_words=max_words)
    return TranscriptIndex(words=tuple(words), utterances=tuple(utterances))


def format_timestamp(seconds: float) -> str:
    """`04:12.3` (o `1:02:03.4` a partir de una hora)."""
    total = round(max(0.0, seconds), 1)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours >= 1:
        return f"{int(hours)}:{int(minutes):02d}:{secs:04.1f}"
    return f"{int(minutes):02d}:{secs:04.1f}"


def serialize_utterance(utterance: Utterance) -> str:
    """Línea compacta que ve el LLM: `[U0012 04:12.3-04:18.9] Texto…`."""
    header = f"{format_timestamp(utterance.start)}-{format_timestamp(utterance.end)}"
    return f"[{utterance.id} {header}] {utterance.text}"


def serialize_utterances(utterances: list[Utterance] | tuple[Utterance, ...]) -> str:
    """Serializa una secuencia de utterances, una por línea."""
    return "\n".join(serialize_utterance(utterance) for utterance in utterances)


def chunk_utterances(
    utterances: list[Utterance] | tuple[Utterance, ...],
    *,
    max_chars: int,
    overlap_ratio: float = DEFAULT_CHUNK_OVERLAP_RATIO,
) -> list[list[Utterance]]:
    """Parte en ventanas por debajo de `max_chars` con solapamiento hacia atrás."""
    items = list(utterances)
    if not items:
        return []
    lines = [serialize_utterance(utterance) for utterance in items]
    total_chars = sum(len(line) + 1 for line in lines)
    if total_chars <= max_chars:
        return [items]

    chunks: list[list[Utterance]] = []
    start = 0
    while start < len(items):
        chars = 0
        end = start
        while end < len(items) and (end == start or chars + len(lines[end]) + 1 <= max_chars):
            chars += len(lines[end]) + 1
            end += 1
        chunks.append(items[start:end])
        if end >= len(items):
            break

        overlap_budget = int(chars * overlap_ratio)
        overlap_chars = 0
        overlap = 0
        cursor = end - 1
        while cursor > start and overlap_chars + len(lines[cursor]) + 1 <= overlap_budget:
            overlap_chars += len(lines[cursor]) + 1
            overlap += 1
            cursor -= 1
        start = max(end - overlap, start + 1)
    return chunks


def nearest_word_range(
    words: list[IndexedWord] | tuple[IndexedWord, ...],
    start: float,
    end: float,
) -> tuple[int, int]:
    """Índices de la palabra cuyo inicio se acerca a `start` y cuyo fin a `end`."""
    if not words:
        raise ValueError("no hay palabras para ajustar el corte")
    first = min(range(len(words)), key=lambda index: (abs(words[index].start - start), index))
    last = min(range(len(words)), key=lambda index: (abs(words[index].end - end), index))
    if last < first:
        last = first
    return first, last


def fit_word_range(
    words: list[IndexedWord] | tuple[IndexedWord, ...],
    first: int,
    last: int,
    *,
    min_duration: float,
    max_duration: float,
    tolerance: float = DEFAULT_SNAP_TOLERANCE_SECONDS,
) -> tuple[int, int] | None:
    """Amplía o recorta el rango hasta cumplir la duración, con margen acotado."""
    base_duration = words[last].end - words[first].start

    while words[last].end - words[first].start < min_duration:
        extended = False
        for candidate_first, candidate_last in ((first, last + 1), (first - 1, last)):
            if not 0 <= candidate_first <= candidate_last < len(words):
                continue
            duration = words[candidate_last].end - words[candidate_first].start
            if duration > max_duration or duration - base_duration > tolerance + 1e-9:
                continue
            first, last = candidate_first, candidate_last
            extended = True
            break
        if not extended:
            break

    while words[last].end - words[first].start > max_duration:
        shrunk = False
        for candidate_first, candidate_last in ((first, last - 1), (first + 1, last)):
            if not 0 <= candidate_first <= candidate_last < len(words):
                continue
            duration = words[candidate_last].end - words[candidate_first].start
            if duration < min_duration or base_duration - duration > tolerance + 1e-9:
                continue
            first, last = candidate_first, candidate_last
            shrunk = True
            break
        if not shrunk:
            break

    duration = words[last].end - words[first].start
    if min_duration <= duration <= max_duration:
        return first, last
    return None


def snap_to_words(
    words: list[IndexedWord] | tuple[IndexedWord, ...],
    start: float,
    end: float,
    *,
    min_duration: float,
    max_duration: float,
    tolerance: float = DEFAULT_SNAP_TOLERANCE_SECONDS,
) -> tuple[int, int] | None:
    """Ajusta un intervalo a límites exactos de palabra o devuelve `None`."""
    if not words:
        return None
    first, last = nearest_word_range(words, start, end)
    return fit_word_range(
        words,
        first,
        last,
        min_duration=min_duration,
        max_duration=max_duration,
        tolerance=tolerance,
    )


def span_text(
    words: list[IndexedWord] | tuple[IndexedWord, ...],
    first: int,
    last: int,
) -> str:
    """Texto exacto del rango de palabras (sin metadatos)."""
    return " ".join(word.text for word in words[first : last + 1])
