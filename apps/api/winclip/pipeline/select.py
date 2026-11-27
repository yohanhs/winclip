"""Selección de clips con LLM y escritura de `selection/candidates.json` (§6.2).

Flujo: cargar transcripción y reglas → utterancear → una pasada o chunks con ranking
global → *snap* determinista a palabras → validación de reglas → resolución de solapes
→ verificación de invariantes → escritura atómica.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from itertools import combinations, pairwise
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from winclip.core.config import Settings, get_settings
from winclip.core.ids import new_ulid
from winclip.core.storage import LocalStorage
from winclip.llm.prompts import load_prompt
from winclip.llm.router import LLMRouter
from winclip.pipeline.schemas import Transcript
from winclip.pipeline.segment import (
    DEFAULT_CHUNK_MAX_CHARS,
    DEFAULT_CHUNK_OVERLAP_RATIO,
    IndexedWord,
    TranscriptIndex,
    build_index,
    chunk_utterances,
    format_timestamp,
    serialize_utterances,
    snap_to_words,
    span_text,
)
from winclip.rules.schema import CampaignRules, RuleViolation, load_rules
from winclip.rules.validator import (
    duration_allowed,
    validate_candidate,
)

CHUNK_CANDIDATES_PER_REQUEST = 10
MAX_MODE_CANDIDATES = 20
DEDUPE_OVERLAP_RATIO = 0.5
ROUND_DECIMALS = 3


class SelectionError(RuntimeError):
    """Error de selección con un mensaje apto para la CLI."""


class MissingTranscriptError(SelectionError):
    """El proyecto no tiene `transcript/transcript.json`."""


class ClipCandidate(BaseModel):
    """Clip propuesto y validado, exacto a `docs/architecture.md §6.2`."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    title: str
    hook: str
    description: str
    hashtags: list[str] = Field(default_factory=list)
    score: int = Field(ge=0, le=100)
    reason: str
    language: str = Field(min_length=1)
    rule_violations: list[RuleViolation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _end_after_start(self) -> ClipCandidate:
        if self.end <= self.start:
            raise ValueError("end debe ser mayor que start")
        return self


class CandidatesDocument(BaseModel):
    """Contrato completo de `selection/candidates.json` (§6.2)."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    campaign_id: str | None = None
    requested: int | Literal["max"]
    provider: str = Field(min_length=1)
    candidates: list[ClipCandidate] = Field(default_factory=list)


class CandidateProposal(BaseModel):
    """Propuesta individual devuelta por el LLM (esquema de respuesta)."""

    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    title: str = ""
    hook: str = ""
    description: str = ""
    hashtags: list[str] = Field(default_factory=list)
    score: int = Field(ge=0, le=100)
    reason: str = ""

    @model_validator(mode="after")
    def _end_after_start(self) -> CandidateProposal:
        if self.end <= self.start:
            raise ValueError("end debe ser mayor que start")
        return self


class SelectionProposal(BaseModel):
    """Respuesta del LLM en una pasada o por ventana."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[CandidateProposal] = Field(default_factory=list)


class RankedItem(BaseModel):
    """Repuntuación de un candidato consolidado por índice."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    score: int = Field(ge=0, le=100)
    reason: str = ""


class RankingProposal(BaseModel):
    """Respuesta del ranking global."""

    model_config = ConfigDict(extra="forbid")

    ranking: list[RankedItem] = Field(default_factory=list)


@dataclass(frozen=True)
class SelectResult:
    """Resultado de `winclip select`."""

    project_id: str
    path: Path
    document: CandidatesDocument
    provider: str
    cached: bool
    chunks: int


def parse_requested(value: int | str) -> int | Literal["max"]:
    """Acepta un entero >= 1 o el literal `max` (case-insensitive)."""
    if isinstance(value, int):
        if value < 1:
            raise SelectionError("--count debe ser un entero >= 1 o 'max'")
        return value
    text = value.strip().lower()
    if text == "max":
        return "max"
    try:
        number = int(text)
    except ValueError as exc:
        raise SelectionError(f"--count inválido: {value!r}; usa un entero >= 1 o 'max'") from exc
    if number < 1:
        raise SelectionError("--count debe ser un entero >= 1 o 'max'")
    return number


def _load_transcript(storage: LocalStorage, project_id: str) -> Transcript:
    path = storage.transcript_path(project_id)
    if not path.is_file():
        raise MissingTranscriptError(
            f"no existe {path}; ejecuta primero `winclip transcribe {project_id}`"
        )
    try:
        return Transcript.model_validate(storage.read_json(path))
    except (ValueError, ValidationError) as exc:
        raise SelectionError(f"transcript inválido en {path}: {exc}") from exc


def _render_rules_block(rules: CampaignRules) -> str:
    lines = [
        f"- Idioma de los metadatos: {rules.language}",
        f"- Duración permitida: {rules.min_duration:g}-{rules.max_duration:g} s",
    ]
    if rules.max_clips is not None:
        lines.append(f"- Máximo de clips: {rules.max_clips}")
    if rules.priority_topics:
        lines.append(f"- Temas prioritarios: {', '.join(rules.priority_topics)}")
    if rules.banned_topics:
        lines.append(f"- Temas prohibidos: {', '.join(rules.banned_topics)}")
    if rules.banned_words:
        lines.append(f"- Palabras prohibidas: {', '.join(rules.banned_words)}")
    if rules.required_keywords:
        lines.append(f"- Palabras clave requeridas: {', '.join(rules.required_keywords)}")
    if rules.tone:
        lines.append(f"- Tono: {rules.tone}")
    lines.append(f"- Gancho máximo: {rules.hook_max_seconds:g} s")
    if rules.cta_text:
        lines.append(f"- CTA: {rules.cta_text}")
    if rules.hashtags:
        lines.append(f"- Hashtags sugeridos: {', '.join(rules.hashtags)}")
    if rules.target_platforms:
        lines.append(f"- Plataformas objetivo: {', '.join(rules.target_platforms)}")
    if rules.extra_instructions:
        lines.append(f"- Instrucciones extra: {rules.extra_instructions}")
    return "\n".join(lines)


def _requested_label(requested: int | Literal["max"], rules: CampaignRules) -> str:
    if requested == "max":
        cap = rules.max_clips or MAX_MODE_CANDIDATES
        return f"todos los que superen el umbral de calidad, hasta {cap}"
    return str(requested)


def _overlap_seconds(
    start_a: float,
    end_a: float,
    start_b: float,
    end_b: float,
) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))


def _overlap_ratio(
    start_a: float,
    end_a: float,
    start_b: float,
    end_b: float,
) -> float:
    intersection = _overlap_seconds(start_a, end_a, start_b, end_b)
    if intersection <= 0:
        return 0.0
    shortest = min(end_a - start_a, end_b - start_b)
    return intersection / shortest if shortest > 0 else 1.0


def _spans_overlap(
    start_a: float,
    end_a: float,
    start_b: float,
    end_b: float,
) -> bool:
    return _overlap_seconds(start_a, end_a, start_b, end_b) > 0


def _dedupe_proposals(proposals: list[CandidateProposal]) -> list[CandidateProposal]:
    """Elimina propuestas con solape >= 50% conservando la de mayor score."""
    kept: list[CandidateProposal] = []
    for proposal in sorted(proposals, key=lambda item: (-item.score, item.start)):
        if any(
            _overlap_ratio(
                proposal.start,
                proposal.end,
                other.start,
                other.end,
            )
            >= DEDUPE_OVERLAP_RATIO
            for other in kept
        ):
            continue
        kept.append(proposal)
    return kept


def _render_candidates_block(proposals: list[CandidateProposal]) -> str:
    lines = []
    for index, proposal in enumerate(proposals):
        header = (
            f"[C{index + 1:04d} score={proposal.score} "
            f"{format_timestamp(proposal.start)}-{format_timestamp(proposal.end)}]"
        )
        lines.append(f"{header} {proposal.title} — {proposal.hook}")
    return "\n".join(lines)


def _apply_ranking(
    proposals: list[CandidateProposal],
    ranking: RankingProposal,
) -> list[CandidateProposal]:
    for item in ranking.ranking:
        if 0 <= item.index < len(proposals):
            proposals[item.index].score = item.score
            if item.reason.strip():
                proposals[item.index].reason = item.reason.strip()
    return sorted(proposals, key=lambda proposal: (-proposal.score, proposal.start))


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _fallback_text(text: str, limit: int) -> str:
    cleaned = _clean_text(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _normalize_hashtags(values: list[str]) -> list[str]:
    tags: list[str] = []
    for raw in values:
        tag = _clean_text(raw)
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = f"#{tag}"
        tag = "#" + tag[1:].replace("#", "").replace(" ", "")
        if tag == "#" or tag in tags:
            continue
        tags.append(tag)
    return tags


def _prepare_candidate(
    proposal: CandidateProposal,
    words: tuple[IndexedWord, ...],
    *,
    rules: CampaignRules,
    language: str,
) -> ClipCandidate | None:
    """Ajusta a palabras, valida duración y reglas y construye el candidato final."""
    span = snap_to_words(
        words,
        proposal.start,
        proposal.end,
        min_duration=rules.min_duration,
        max_duration=rules.max_duration,
    )
    if span is None:
        return None
    first, last = span
    start = round(words[first].start, ROUND_DECIMALS)
    end = round(words[last].end, ROUND_DECIMALS)
    if not duration_allowed(start, end, rules):
        return None

    clip_text = span_text(words, first, last)
    title = _clean_text(proposal.title) or _fallback_text(clip_text, 70)
    hook = _clean_text(proposal.hook) or _fallback_text(clip_text, 90)
    description = _clean_text(proposal.description)
    if rules.cta_text and rules.cta_text.casefold() not in description.casefold():
        description = (
            f"{description}\n\n{rules.cta_text}".strip() if description else rules.cta_text
        )
    hashtags = _normalize_hashtags(proposal.hashtags)
    violations = validate_candidate(
        start=start,
        end=end,
        rules=rules,
        clip_text=clip_text,
        title=title,
        hook=hook,
        description=description,
        hashtags=hashtags,
    )

    return ClipCandidate(
        id=new_ulid(),
        start=start,
        end=end,
        title=title,
        hook=hook,
        description=description,
        hashtags=hashtags,
        score=proposal.score,
        reason=_clean_text(proposal.reason) or "propuesta del modelo",
        language=language,
        rule_violations=violations,
    )


def _select_final(
    candidates: list[ClipCandidate],
    requested: int | Literal["max"],
    rules: CampaignRules,
    threshold: int,
) -> list[ClipCandidate]:
    """Resuelve solapes de forma codiciosa y aplica el modo N o `max`."""
    clean = sorted(
        (candidate for candidate in candidates if not candidate.rule_violations),
        key=lambda candidate: (-candidate.score, candidate.start),
    )
    warned = sorted(
        (candidate for candidate in candidates if candidate.rule_violations),
        key=lambda candidate: (-candidate.score, candidate.start),
    )
    if requested == "max":
        queue = clean
        limit = rules.max_clips
    else:
        queue = clean + warned
        limit = requested if rules.max_clips is None else min(requested, rules.max_clips)

    chosen: list[ClipCandidate] = []
    for candidate in queue:
        if requested == "max" and candidate.score < threshold:
            continue
        if limit is not None and len(chosen) >= limit:
            break
        if any(
            _spans_overlap(candidate.start, candidate.end, other.start, other.end)
            for other in chosen
        ):
            continue
        chosen.append(candidate)

    chosen.sort(key=lambda candidate: (-candidate.score, candidate.start))
    return chosen


def _verify_invariants(
    candidates: list[ClipCandidate],
    words: tuple[IndexedWord, ...],
    rules: CampaignRules,
) -> None:
    """Comprueba corte en palabras, duración, solapes y orden antes de escribir."""
    word_starts = {round(word.start, ROUND_DECIMALS) for word in words}
    word_ends = {round(word.end, ROUND_DECIMALS) for word in words}
    for candidate in candidates:
        if candidate.start not in word_starts:
            raise SelectionError(
                f"invariante roto: start={candidate.start} no coincide con ninguna palabra"
            )
        if candidate.end not in word_ends:
            raise SelectionError(
                f"invariante roto: end={candidate.end} no coincide con ninguna palabra"
            )
        if not duration_allowed(candidate.start, candidate.end, rules):
            raise SelectionError(
                f"invariante roto: duración {candidate.end - candidate.start:.1f}s fuera de rango"
            )
    for first, second in combinations(candidates, 2):
        if _spans_overlap(first.start, first.end, second.start, second.end):
            raise SelectionError("invariante roto: hay candidatos solapados")
    for previous, following in pairwise(candidates):
        if previous.score < following.score:
            raise SelectionError("invariante roto: los candidatos no están ordenados por score")


def select_clips(
    project_id: str,
    *,
    settings: Settings | None = None,
    count: int | str = 10,
    rules_path: Path | str | None = None,
    rules: CampaignRules | None = None,
    campaign_id: str | None = None,
    use_cache: bool = True,
    router: LLMRouter | None = None,
    router_factory: Callable[[], LLMRouter] | None = None,
    storage: LocalStorage | None = None,
) -> SelectResult:
    """Selecciona clips, escribe `selection/candidates.json` y lo devuelve."""
    settings = settings or get_settings()
    storage = storage or LocalStorage(settings.storage_dir)
    requested = parse_requested(count)
    active_rules = (
        rules
        if rules is not None
        else (load_rules(rules_path) if rules_path is not None else CampaignRules())
    )
    rules = active_rules

    transcript = _load_transcript(storage, project_id)
    index = _build_index(transcript)
    if not index.utterances:
        raise SelectionError("la transcripción no contiene palabras con timestamps")

    language = rules.language if rules.language != "auto" else transcript.language
    rules_block = _render_rules_block(rules)
    if router is None:
        router = router_factory() if router_factory is not None else LLMRouter(settings)

    utterance_text = serialize_utterances(index.utterances)
    provider_id = ""
    cached = False
    chunks = 1
    proposals: list[CandidateProposal]

    if len(utterance_text) <= settings.llm_single_pass_max_chars:
        template = load_prompt("select_single_v1")
        system = template.render(
            language=language,
            min_duration=rules.min_duration,
            max_duration=rules.max_duration,
            requested=_requested_label(requested, rules),
            rules_block=rules_block,
        )
        result = router.complete_json(
            system,
            utterance_text,
            SelectionProposal,
            logical_model=template.logical_model,
            use_cache=use_cache,
        )
        proposals = list(result.data.candidates)
        provider_id = result.provider_id
        cached = result.cached
    else:
        chunk_chars = min(DEFAULT_CHUNK_MAX_CHARS, settings.llm_single_pass_max_chars)
        chunk_list = chunk_utterances(
            index.utterances,
            max_chars=chunk_chars,
            overlap_ratio=DEFAULT_CHUNK_OVERLAP_RATIO,
        )
        template = load_prompt("select_chunk_v1")
        chunks = len(chunk_list)
        proposals = []
        for position, chunk in enumerate(chunk_list, start=1):
            system = template.render(
                language=language,
                min_duration=rules.min_duration,
                max_duration=rules.max_duration,
                requested=min(requested, CHUNK_CANDIDATES_PER_REQUEST)
                if requested != "max"
                else CHUNK_CANDIDATES_PER_REQUEST,
                chunk_index=position,
                chunk_total=chunks,
                rules_block=rules_block,
            )
            chunk_result = router.complete_json(
                system,
                serialize_utterances(chunk),
                SelectionProposal,
                logical_model=template.logical_model,
                use_cache=use_cache,
            )
            proposals.extend(chunk_result.data.candidates)
            provider_id = chunk_result.provider_id
            cached = cached or chunk_result.cached

        consolidated = _dedupe_proposals(proposals)
        if consolidated:
            rank_template = load_prompt("select_rank_v1")
            rank_system = rank_template.render(
                language=language,
                min_duration=rules.min_duration,
                max_duration=rules.max_duration,
                rules_block=rules_block,
            )
            rank_result = router.complete_json(
                rank_system,
                _render_candidates_block(consolidated),
                RankingProposal,
                logical_model=rank_template.logical_model,
                use_cache=use_cache,
            )
            proposals = _apply_ranking(consolidated, rank_result.data)
            provider_id = rank_result.provider_id
            cached = cached or rank_result.cached

    prepared = [
        candidate
        for proposal in proposals
        if (
            candidate := _prepare_candidate(
                proposal,
                index.words,
                rules=rules,
                language=language,
            )
        )
        is not None
    ]
    final = _select_final(prepared, requested, rules, settings.llm_score_threshold)
    _verify_invariants(final, index.words, rules)

    document = CandidatesDocument(
        project_id=project_id,
        campaign_id=campaign_id,
        requested=requested,
        provider=provider_id,
        candidates=final,
    )
    path = storage.write_json_atomic(storage.selection_path(project_id), document)
    return SelectResult(
        project_id=project_id,
        path=path,
        document=document,
        provider=provider_id,
        cached=cached,
        chunks=chunks,
    )


def _build_index(transcript: Transcript) -> TranscriptIndex:
    """Aplana palabras y construye utterances de la transcripción."""
    return build_index(transcript)


def load_candidates(path: Path) -> CandidatesDocument:
    """Lee un `candidates.json` ya escrito (útil para tests y para el worker)."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return CandidatesDocument.model_validate(payload)
