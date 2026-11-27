"""Tests de selección de clips y worker con y sin campaña asociada."""

from __future__ import annotations

from pathlib import Path

from fakes import FakeSelectionProvider
from sqlmodel import Session, select

from winclip.core.config import Settings
from winclip.core.db import ensure_default_workspace, init_db
from winclip.core.ids import new_project_id, new_ulid
from winclip.core.models import Campaign, Clip, Project
from winclip.core.storage import LocalStorage
from winclip.llm.router import LLMRouter
from winclip.pipeline.schemas import Transcript, TranscriptSegment, WordTimestamp
from winclip.pipeline.select import select_clips
from winclip.rules.schema import CampaignRules
from winclip.worker import queue
from winclip.worker.handlers import PipelineBackends, handle_job


def _settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, storage_dir=tmp_path / "storage")


def _write_transcript(settings: Settings, project_id: str) -> None:
    segments = []
    base = 0.0
    texts = [
        ("inversion", "compuesta", "segura."),
        ("dinero", "facil", "garantizado."),
        ("ahorro", "constante", "disciplina."),
    ]
    for idx, triple in enumerate(texts):
        words = [
            WordTimestamp(w=w, s=base + i * 2.5, e=base + i * 2.5 + 2.5, p=0.95)
            for i, w in enumerate(triple)
        ]
        segments.append(
            TranscriptSegment(
                id=idx,
                start=words[0].s,
                end=words[-1].e,
                text=" ".join(w.w for w in words),
                words=words,
            )
        )
        base += 8.0
    transcript = Transcript(
        language="es",
        duration=segments[-1].end,
        model="fake",
        segments=segments,
    )
    storage = LocalStorage(settings.storage_dir)
    storage.write_json_atomic(storage.transcript_path(project_id), transcript)


def _router(settings: Settings, provider: FakeSelectionProvider) -> LLMRouter:
    return LLMRouter(
        settings,
        {provider.name: provider},
        sleep_fn=lambda _s: None,
        jitter_fn=lambda: 0.0,
    )


def test_select_with_and_without_campaign(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    project_id = new_project_id()
    _write_transcript(settings, project_id)

    # Sin campaña
    provider_plain = FakeSelectionProvider("fake", "fake-1", candidates_per_request=3)
    plain = select_clips(
        project_id,
        settings=settings,
        count=3,
        rules=CampaignRules(min_duration=5, max_duration=30),
        router=_router(settings, provider_plain),
        use_cache=False,
    )
    assert plain.document.campaign_id is None
    assert all(c.rule_violations == [] for c in plain.document.candidates)

    # Con campaña: reglas inyectadas en prompt + rule_violations pobladas
    campaign_rules = CampaignRules(
        name="Finanzas ES",
        language="es",
        min_duration=5,
        max_duration=30,
        banned_words=["garantizado"],
        required_keywords=["inversión"],
        hashtags=["#finanzas", "#shorts"],
        cta_text="Suscríbete para más finanzas",
        target_platforms=["youtube", "tiktok"],
        extra_instructions="Prioriza claridad financiera.",
    )
    provider_campaign = FakeSelectionProvider("fake", "fake-1", candidates_per_request=3)
    with_campaign = select_clips(
        project_id,
        settings=settings,
        count=3,
        rules=campaign_rules,
        campaign_id="01campaignid",
        router=_router(settings, provider_campaign),
        use_cache=False,
    )

    assert with_campaign.document.campaign_id == "01campaignid"
    system_prompt = provider_campaign.calls[0][0]
    assert "garantizado" in system_prompt
    assert "#finanzas" in system_prompt
    assert "youtube, tiktok" in system_prompt
    assert "Prioriza claridad financiera." in system_prompt

    # Todos los clips incluyen el CTA sugerido en la descripción y violaciones deterministas
    assert len(with_campaign.document.candidates) == 3
    for cand in with_campaign.document.candidates:
        assert "Suscríbete para más finanzas" in cand.description
        codes = {v.code for v in cand.rule_violations}
        assert "missing_required_hashtag" in codes

    # El tramo que contiene "garantizado" registra banned_word_present
    banned_cand = next(c for c in with_campaign.document.candidates if abs(c.start - 8.0) < 0.1)
    assert any(v.code == "banned_word_present" for v in banned_cand.rule_violations)


def test_worker_select_persists_campaign_rule_violations_in_clip_table(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = init_db(settings)
    project_id = new_project_id()
    _write_transcript(settings, project_id)

    rules = CampaignRules(
        name="Campaña Worker",
        language="es",
        min_duration=5,
        max_duration=30,
        banned_words=["garantizado"],
        required_keywords=["inversión"],
        hashtags=["#finanzas"],
    )
    campaign_id = new_ulid()
    with Session(engine) as session:
        ws = ensure_default_workspace(session)
        session.add(
            Campaign(
                id=campaign_id,
                workspace_id=ws.id,
                name=rules.name,
                rules_json=rules.model_dump(mode="json"),
            )
        )
        session.add(
            Project(
                id=project_id,
                workspace_id=ws.id,
                campaign_id=campaign_id,
                source_type="file",
                title="Video de finanzas",
                requested_clips=3,
                language="es",
            )
        )
        session.commit()

    provider = FakeSelectionProvider("fake", "fake-1", candidates_per_request=3)

    def _select_with_fake(pid: str, **kwargs):
        return select_clips(pid, router=_router(settings, provider), use_cache=False, **kwargs)

    job = queue.enqueue(engine, job_type="select", project_id=project_id)
    finished = handle_job(
        engine,
        job.id,
        settings=settings,
        backends=PipelineBackends(select=_select_with_fake, poll_seconds=0.01),
    )
    assert finished.status == "done"

    with Session(engine) as session:
        clips = list(session.exec(select(Clip).where(Clip.project_id == project_id)).all())
    assert len(clips) == 3
    all_codes = [
        v["code"] for clip in clips for v in (clip.candidate or {}).get("rule_violations", [])
    ]
    assert "banned_word_present" in all_codes
    assert "missing_required_hashtag" in all_codes
