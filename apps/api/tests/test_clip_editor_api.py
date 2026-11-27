"""Tests de API y validación para el editor avanzado de clips (`add-clip-editor-controls`)."""

from __future__ import annotations

import pytest
from api_helpers import seed_clip, seed_project
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlmodel import Session

from winclip.core.models import Clip
from winclip.core.storage import LocalStorage
from winclip.pipeline.schemas import Transcript, TranscriptSegment, WordTimestamp
from winclip.pipeline.subtitles.layout import word_override_key
from winclip.routers.schemas import ClipUpdate


def _write_transcript(storage: LocalStorage, project_id: str) -> Transcript:
    transcript = Transcript(
        language="es",
        duration=60.0,
        model="fake-whisper",
        segments=[
            TranscriptSegment(
                id=0,
                start=0.0,
                end=12.0,
                text="Antes Hola Juc de prueba después",
                words=[
                    WordTimestamp(w="Antes", s=0.2, e=0.6, p=0.99),
                    WordTimestamp(w="Hola", s=1.2, e=1.5, p=0.98),
                    WordTimestamp(w="Juc", s=1.6, e=2.0, p=0.91),
                    WordTimestamp(w="de", s=2.1, e=2.3, p=0.97),
                    WordTimestamp(w="prueba", s=2.4, e=3.0, p=0.96),
                    WordTimestamp(w="después", s=35.0, e=35.5, p=0.99),
                ],
            )
        ],
    )
    storage.write_json_atomic(storage.transcript_path(project_id), transcript)
    return transcript


# --------------------------------------------------------------------------- validación Pydantic


@pytest.mark.parametrize(
    "payload",
    [
        {"subtitle_preset": "preset-que-no-existe"},
        {"subtitle_preset": "   "},
        {"reframe_mode": "invalid-mode"},
        {"crop_x_pct": -1.0},
        {"crop_x_pct": 100.5},
        {"crop_y_pct": -0.1},
        {"crop_y_pct": 101.0},
        {"zoom_pct": 49.9},
        {"zoom_pct": 200.1},
        {"subtitle_overrides": {"1600:2000": "x" * 65}},
        {"subtitle_overrides": {"   ": "Hook"}},
    ],
)
def test_clip_update_rejects_invalid_editor_fields(payload: dict) -> None:
    with pytest.raises(ValidationError):
        ClipUpdate.model_validate(payload)


def test_clip_update_accepts_valid_editor_fields() -> None:
    update = ClipUpdate.model_validate(
        {
            "subtitle_preset": "clean-white",
            "reframe_mode": "center",
            "crop_x_pct": 35.0,
            "crop_y_pct": 25.0,
            "zoom_pct": 120.0,
            "subtitle_overrides": {"1600:2000": "Hook"},
        }
    )
    assert update.subtitle_preset == "clean-white"
    assert update.reframe_mode == "center"
    assert update.crop_x_pct == 35.0
    assert update.crop_y_pct == 25.0
    assert update.zoom_pct == 120.0
    assert update.subtitle_overrides == {"1600:2000": "Hook"}


# --------------------------------------------------------------------------- GET /words & PATCH


def test_get_clip_words_returns_range_and_applies_overrides(
    api_client: TestClient, api_settings
) -> None:
    storage = LocalStorage(api_settings.storage_dir)
    project = seed_project(api_client.app.state.engine, storage=storage)
    clip = seed_clip(api_client.app.state.engine, storage, project.id)
    _write_transcript(storage, project.id)

    # Lectura inicial sin overrides
    initial = api_client.get(f"/api/clips/{clip.id}/words")
    assert initial.status_code == 200
    body = initial.json()
    assert body["clip_id"] == clip.id
    words = body["words"]
    assert [w["original"] for w in words] == ["Hola", "Juc", "de", "prueba"]
    assert [w["index"] for w in words] == [0, 1, 2, 3]
    assert all(not w["edited"] for w in words)

    juc_word = words[1]
    assert juc_word["key"] == word_override_key(1.6, 2.0) == "1600:2000"
    assert juc_word["start"] == 0.6
    assert juc_word["end"] == 1.0

    # Guardar corrección de palabra
    patched = api_client.patch(
        f"/api/clips/{clip.id}",
        json={"subtitle_overrides": {juc_word["key"]: "Hook"}},
    )
    assert patched.status_code == 200
    assert patched.json()["subtitle_overrides"] == {"1600:2000": "Hook"}

    # Leer de nuevo: original intacto, text actualizado, timestamps iguales
    after = api_client.get(f"/api/clips/{clip.id}/words")
    assert after.status_code == 200
    updated_words = after.json()["words"]
    assert updated_words[1]["original"] == "Juc"
    assert updated_words[1]["text"] == "Hook"
    assert updated_words[1]["edited"] is True
    assert updated_words[1]["start"] == juc_word["start"]
    assert updated_words[1]["end"] == juc_word["end"]

    # Ampliar start_sec hacia atrás: la corrección sigue anclada a "Juc" por clave timestamp
    trimmed = api_client.patch(f"/api/clips/{clip.id}", json={"start_sec": 0.0})
    assert trimmed.status_code == 200
    expanded = api_client.get(f"/api/clips/{clip.id}/words").json()["words"]
    assert [w["original"] for w in expanded] == ["Antes", "Hola", "Juc", "de", "prueba"]
    assert expanded[2]["original"] == "Juc"
    assert expanded[2]["text"] == "Hook"
    assert expanded[2]["edited"] is True
    assert expanded[1]["edited"] is False

    # Restablecer correcciones
    reset = api_client.patch(f"/api/clips/{clip.id}", json={"subtitle_overrides": {}})
    assert reset.status_code == 200
    assert reset.json()["subtitle_overrides"] == {}
    restored = api_client.get(f"/api/clips/{clip.id}/words").json()["words"]
    assert restored[2]["text"] == "Juc"
    assert restored[2]["edited"] is False


def test_get_clip_words_404_when_missing_clip_or_transcript(
    api_client: TestClient, api_settings
) -> None:
    storage = LocalStorage(api_settings.storage_dir)
    project = seed_project(api_client.app.state.engine, storage=storage)
    clip = seed_clip(api_client.app.state.engine, storage, project.id)

    assert api_client.get("/api/clips/no-existe/words").status_code == 404
    no_transcript = api_client.get(f"/api/clips/{clip.id}/words")
    assert no_transcript.status_code == 404
    assert "transcripción" in no_transcript.json()["detail"].lower()


def test_patch_clip_persists_and_clears_render_overrides(
    api_client: TestClient, api_settings
) -> None:
    storage = LocalStorage(api_settings.storage_dir)
    project = seed_project(api_client.app.state.engine, storage=storage)
    clip = seed_clip(api_client.app.state.engine, storage, project.id)

    resp = api_client.patch(
        f"/api/clips/{clip.id}",
        json={
            "subtitle_preset": "clean-white",
            "reframe_mode": "center",
            "crop_x_pct": 35.0,
            "crop_y_pct": 25.0,
            "zoom_pct": 120.0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["subtitle_preset"] == "clean-white"
    assert data["reframe_mode"] == "center"
    assert data["crop_x_pct"] == 35.0
    assert data["crop_y_pct"] == 25.0
    assert data["zoom_pct"] == 120.0

    with Session(api_client.app.state.engine) as session:
        stored = session.get(Clip, clip.id)
    assert stored is not None
    assert stored.render_overrides == {
        "subtitle_preset": "clean-white",
        "reframe_mode": "center",
        "crop_x_pct": 35.0,
        "crop_y_pct": 25.0,
        "zoom_pct": 120.0,
    }

    # Limpiar preset y reframe (vuelve a heredar del proyecto)
    cleared = api_client.patch(
        f"/api/clips/{clip.id}",
        json={"subtitle_preset": None, "reframe_mode": None},
    )
    assert cleared.status_code == 200
    cleared_data = cleared.json()
    assert cleared_data["subtitle_preset"] is None
    assert cleared_data["reframe_mode"] is None
    assert cleared_data["crop_x_pct"] == 35.0


def test_patch_clip_422_does_not_mutate_clip(api_client: TestClient, api_settings) -> None:
    storage = LocalStorage(api_settings.storage_dir)
    project = seed_project(api_client.app.state.engine, storage=storage)
    clip = seed_clip(api_client.app.state.engine, storage, project.id)

    for bad in (
        {"subtitle_preset": "desconocido"},
        {"reframe_mode": "wide"},
        {"crop_x_pct": 150.0},
        {"crop_y_pct": -5.0},
        {"zoom_pct": 250.0},
        {"zoom_pct": 20.0},
        {"subtitle_overrides": {"1000:1200": "a" * 65}},
    ):
        resp = api_client.patch(f"/api/clips/{clip.id}", json=bad)
        assert resp.status_code == 422, bad

    with Session(api_client.app.state.engine) as session:
        stored = session.get(Clip, clip.id)
    assert stored is not None
    assert stored.render_overrides is None
    assert stored.subtitle_overrides is None


def test_openapi_declares_get_clip_words_operation_id(api_client: TestClient) -> None:
    schema = api_client.get("/openapi.json").json()
    words_op = schema["paths"]["/api/clips/{clip_id}/words"]["get"]
    assert words_op["operationId"] == "getClipWords"
