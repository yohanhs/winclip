"""Tests de resolución en cascada de overrides por clip en `worker/handlers.py`."""

from __future__ import annotations

from types import SimpleNamespace

from api_helpers import seed_clip, seed_project
from fastapi.testclient import TestClient
from sqlmodel import Session

from winclip.core.db import ensure_default_workspace
from winclip.core.ids import new_ulid
from winclip.core.models import Campaign, Clip, Project
from winclip.core.storage import LocalStorage
from winclip.pipeline.render_models import RenderOptions
from winclip.rules.schema import CampaignRules
from winclip.worker import queue
from winclip.worker.handlers import PipelineBackends, _render_options, handle_job


def _fake_manifest(clip_id: str, candidate_id: str, storage: LocalStorage, project_id: str):
    clip_dir = storage.clip_dir(project_id, clip_id)
    clip_dir.mkdir(parents=True, exist_ok=True)
    (clip_dir / "clip.mp4").write_bytes(b"mp4")
    (clip_dir / "thumb.jpg").write_bytes(b"jpg")
    return SimpleNamespace(clip_id=clip_id, candidate_id=candidate_id, duration=20.0)


def test_render_options_cascade_clip_over_campaign_over_project(api_settings) -> None:
    storage = LocalStorage(api_settings.storage_dir)
    project = Project(
        id=new_ulid(),
        workspace_id="ws1",
        subtitle_preset="bold-yellow",
        reframe_mode="face",
    )
    campaign_rules = CampaignRules(name="Campaña", subtitle_preset="hormozi")

    # Sin overrides en el clip: hereda campaña > proyecto
    clip_inherit = Clip(id=new_ulid(), project_id=project.id)
    opts_inherit = _render_options(
        project,
        force=True,
        clip=clip_inherit,
        campaign_rules=campaign_rules,
        storage=storage,
    )
    assert opts_inherit.preset == "hormozi"
    assert opts_inherit.reframe == "face"
    assert opts_inherit.crop_x_pct == 50.0
    assert opts_inherit.crop_y_pct == 50.0
    assert opts_inherit.zoom_pct == 100.0
    assert opts_inherit.word_overrides == {}

    # Sin campaña: hereda proyecto
    opts_project = _render_options(
        project,
        force=True,
        clip=clip_inherit,
        campaign_rules=None,
        storage=storage,
    )
    assert opts_project.preset == "bold-yellow"

    # Con overrides en el clip: gana el clip sobre campaña y proyecto
    clip_custom = Clip(
        id=new_ulid(),
        project_id=project.id,
        render_overrides={
            "subtitle_preset": "clean-white",
            "reframe_mode": "center",
            "crop_x_pct": 35.0,
            "crop_y_pct": 25.0,
            "zoom_pct": 120.0,
        },
        subtitle_overrides={"1500:1900": "Hook"},
    )
    opts_custom = _render_options(
        project,
        force=True,
        clip=clip_custom,
        campaign_rules=campaign_rules,
        storage=storage,
    )
    assert opts_custom.preset == "clean-white"
    assert opts_custom.reframe == "center"
    assert opts_custom.crop_x_pct == 35.0
    assert opts_custom.crop_y_pct == 25.0
    assert opts_custom.zoom_pct == 120.0
    assert opts_custom.word_overrides == {"1500:1900": "Hook"}


def test_worker_isolates_overrides_between_clips_of_same_project(
    api_client: TestClient, api_settings
) -> None:
    engine = api_client.app.state.engine
    storage = LocalStorage(api_settings.storage_dir)

    with Session(engine) as session:
        ws = ensure_default_workspace(session)
        campaign = Campaign(
            id=new_ulid(),
            workspace_id=ws.id,
            name="Campaña Hormozi",
            rules_json=CampaignRules(name="Campaña Hormozi", subtitle_preset="hormozi").model_dump(
                mode="json"
            ),
        )
        session.add(campaign)
        session.commit()
        campaign_id = campaign.id

    project = seed_project(
        engine,
        storage=storage,
        subtitle_preset="bold-yellow",
        reframe_mode="face",
    )
    with Session(engine) as session:
        stored_proj = session.get(Project, project.id)
        assert stored_proj is not None
        stored_proj.campaign_id = campaign_id
        session.add(stored_proj)
        session.commit()

    clip_a = seed_clip(engine, storage, project.id, title="Clip A")
    clip_b = seed_clip(engine, storage, project.id, title="Clip B")

    with Session(engine) as session:
        a = session.get(Clip, clip_a.id)
        assert a is not None
        a.render_overrides = {
            "subtitle_preset": "clean-white",
            "reframe_mode": "blur",
            "crop_x_pct": 35.0,
            "crop_y_pct": 25.0,
            "zoom_pct": 120.0,
        }
        a.subtitle_overrides = {"1600:2000": "Hook"}
        session.add(a)
        session.commit()

    captured: dict[str, RenderOptions] = {}

    def fake_render(project_id, candidate_id, options, *, settings, on_progress, clip_id):
        captured[clip_id] = options
        return _fake_manifest(clip_id, candidate_id, storage, project_id)

    backends = PipelineBackends(render=fake_render)

    # Re-render clip A y luego clip B por separado
    for target_id in (clip_a.id, clip_b.id):
        job = queue.enqueue(
            engine, job_type="render", project_id=project.id, payload={"clip_id": target_id}
        )
        claimed = queue.claim_next(engine, worker_id="w1", light_running=0, light_limit=2)
        assert claimed is not None and claimed.id == job.id
        finished = handle_job(engine, job.id, settings=api_settings, backends=backends)
        assert finished.status == "done"

    assert captured[clip_a.id].preset == "clean-white"
    assert captured[clip_a.id].reframe == "blur"
    assert captured[clip_a.id].crop_x_pct == 35.0
    assert captured[clip_a.id].crop_y_pct == 25.0
    assert captured[clip_a.id].zoom_pct == 120.0
    assert captured[clip_a.id].word_overrides == {"1600:2000": "Hook"}

    # Clip B no se ve afectado por los overrides de Clip A
    assert captured[clip_b.id].preset == "hormozi"
    assert captured[clip_b.id].reframe == "face"
    assert captured[clip_b.id].crop_x_pct == 50.0
    assert captured[clip_b.id].crop_y_pct == 50.0
    assert captured[clip_b.id].zoom_pct == 100.0
    assert captured[clip_b.id].word_overrides == {}
