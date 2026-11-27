"""Tests de `/api/campaigns`: CRUD, duplicado, plantillas, parseo, watermark y FK."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from winclip.rules.parser import BriefParseError, ParsedCampaignDraft
from winclip.rules.schema import CampaignRules


def _sample_rules(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Campaña Finanzas",
        "language": "es",
        "min_duration": 20,
        "max_duration": 60,
        "max_clips": 8,
        "priority_topics": ["ahorro", "inversión"],
        "banned_topics": ["cripto"],
        "banned_words": ["garantizado"],
        "required_keywords": ["inversión"],
        "tone": "educativo",
        "hook_max_seconds": 3,
        "cta_text": "Suscríbete al canal",
        "hashtags": ["#finanzas", "#shorts"],
        "subtitle_preset": "bold-yellow",
        "watermark_path": None,
        "target_platforms": ["youtube", "tiktok"],
        "extra_instructions": "Sin relleno inicial",
    }
    payload.update(overrides)
    return payload


def _png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGBA", (32, 32), (245, 158, 11, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _webp_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGBA", (32, 32), (16, 185, 129, 255)).save(buf, format="WEBP")
    return buf.getvalue()


def test_campaigns_crud_and_duplicate(api_client) -> None:
    empty = api_client.get("/api/campaigns")
    assert empty.status_code == 200
    assert empty.json() == []

    created = api_client.post(
        "/api/campaigns",
        json={
            "name": "Campaña Finanzas",
            "rules": _sample_rules(),
            "source_text": "Brief original de finanzas.",
        },
    )
    assert created.status_code == 201
    campaign = created.json()
    campaign_id = campaign["id"]
    assert campaign["name"] == "Campaña Finanzas"
    assert campaign["rules"]["hashtags"] == ["#finanzas", "#shorts"]
    assert campaign["source_text"] == "Brief original de finanzas."
    assert campaign["projects_count"] == 0

    fetched = api_client.get(f"/api/campaigns/{campaign_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == campaign_id

    updated = api_client.patch(
        f"/api/campaigns/{campaign_id}",
        json={
            "name": "Campaña Finanzas v2",
            "rules": _sample_rules(name="Campaña Finanzas v2", max_duration=55),
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Campaña Finanzas v2"
    assert updated.json()["rules"]["max_duration"] == 55

    duplicated = api_client.post(f"/api/campaigns/{campaign_id}/duplicate")
    assert duplicated.status_code == 201
    copy = duplicated.json()
    assert copy["id"] != campaign_id
    assert copy["name"] == "Campaña Finanzas v2 (copia)"
    assert copy["rules"]["max_duration"] == 55
    assert copy["source_text"] == "Brief original de finanzas."

    listing = api_client.get("/api/campaigns")
    assert listing.status_code == 200
    assert len(listing.json()) == 2

    deleted = api_client.delete(f"/api/campaigns/{copy['id']}")
    assert deleted.status_code == 204
    assert api_client.get(f"/api/campaigns/{copy['id']}").status_code == 404


def test_delete_campaign_sets_project_campaign_id_to_null(api_client) -> None:
    created = api_client.post(
        "/api/campaigns",
        json={"name": "Podcast ES", "rules": _sample_rules(name="Podcast ES", max_clips=6)},
    )
    assert created.status_code == 201
    campaign_id = created.json()["id"]

    project_resp = api_client.post(
        "/api/projects",
        json={
            "source_url": "https://www.youtube.com/watch?v=abc12345678",
            "campaign_id": campaign_id,
        },
    )
    assert project_resp.status_code == 201
    project = project_resp.json()["project"]
    assert project["campaign_id"] == campaign_id
    assert project["campaign_name"] == "Podcast ES"
    # Herencia por defecto desde la campaña cuando el cliente no lo especifica
    assert project["requested_clips"] == 6
    assert project["language"] == "es"
    assert project["subtitle_preset"] == "bold-yellow"

    # Eliminar campaña conserva el proyecto y vacía campaign_id (ON DELETE SET NULL)
    deleted = api_client.delete(f"/api/campaigns/{campaign_id}")
    assert deleted.status_code == 204

    project_after = api_client.get(f"/api/projects/{project['id']}")
    assert project_after.status_code == 200
    assert project_after.json()["campaign_id"] is None
    assert project_after.json()["campaign_name"] is None


def test_create_project_rejects_unknown_campaign_id(api_client) -> None:
    resp = api_client.post(
        "/api/projects",
        json={
            "source_url": "https://www.youtube.com/watch?v=abc12345678",
            "campaign_id": "nonexistentcampaignid",
        },
    )
    assert resp.status_code == 422


def test_campaigns_validation_errors_422(api_client) -> None:
    bad_duration = api_client.post(
        "/api/campaigns",
        json={"name": "Mala", "rules": _sample_rules(min_duration=60, max_duration=30)},
    )
    assert bad_duration.status_code == 422

    bad_preset = api_client.post(
        "/api/campaigns",
        json={"name": "Mala", "rules": _sample_rules(subtitle_preset="inventado")},
    )
    assert bad_preset.status_code == 422

    bad_watermark = api_client.post(
        "/api/campaigns",
        json={"name": "Mala", "rules": _sample_rules(watermark_path="/etc/passwd.png")},
    )
    assert bad_watermark.status_code == 422

    traversal = api_client.post(
        "/api/campaigns",
        json={
            "name": "Mala",
            "rules": _sample_rules(watermark_path="campaigns/../../secret.png"),
        },
    )
    assert traversal.status_code == 422


def test_campaigns_templates_endpoint(api_client) -> None:
    resp = api_client.get("/api/campaigns/templates")
    assert resp.status_code == 200
    templates = resp.json()
    assert len(templates) >= 4
    langs = [tpl["language"] for tpl in templates]
    assert langs.count("es") >= 2
    assert langs.count("en") >= 2


def test_campaigns_parse_endpoint_success_and_error(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_parse(source_text: str, **_kwargs: Any) -> ParsedCampaignDraft:
        return ParsedCampaignDraft(
            rules=CampaignRules(name="Brief Parseado", language="es", hashtags=["#clips"]),
            inferred_fields=["tone", "subtitle_preset"],
            warnings=[],
            provider="fake:model",
        )

    monkeypatch.setattr("winclip.routers.campaigns.parse_campaign_brief", _fake_parse)
    ok = api_client.post("/api/campaigns/parse", json={"source_text": "Clips cortos con #clips"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["rules"]["name"] == "Brief Parseado"
    assert body["inferred_fields"] == ["tone", "subtitle_preset"]
    assert body["provider"] == "fake:model"
    # No persiste automáticamente
    assert api_client.get("/api/campaigns").json() == []

    def _failing_parse(_source_text: str, **_kwargs: Any) -> ParsedCampaignDraft:
        raise BriefParseError("sin proveedores LLM disponibles")

    monkeypatch.setattr("winclip.routers.campaigns.parse_campaign_brief", _failing_parse)
    err = api_client.post("/api/campaigns/parse", json={"source_text": "Otro brief"})
    assert err.status_code == 503


def test_campaigns_watermark_upload_and_security(api_client, api_settings) -> None:
    png_resp = api_client.post(
        "/api/campaigns/watermarks",
        files={"file": ("logo.png", _png_bytes(), "image/png")},
    )
    assert png_resp.status_code == 201
    wm_path = png_resp.json()["watermark_path"]
    assert wm_path.startswith("campaigns/watermarks/")
    assert wm_path.endswith(".png")
    assert (Path(api_settings.storage_dir) / wm_path).is_file()

    filename = Path(wm_path).name
    served = api_client.get(f"/api/campaigns/watermarks/{filename}")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"

    webp_resp = api_client.post(
        "/api/campaigns/watermarks",
        files={"file": ("brand.webp", _webp_bytes(), "image/webp")},
    )
    assert webp_resp.status_code == 201
    assert webp_resp.json()["watermark_path"].endswith(".webp")

    # MIME inválido
    bad_mime = api_client.post(
        "/api/campaigns/watermarks",
        files={"file": ("photo.jpg", b"not-a-png", "image/jpeg")},
    )
    assert bad_mime.status_code == 422

    # Firma de archivo inválida con MIME image/png falso
    fake_png = api_client.post(
        "/api/campaigns/watermarks",
        files={"file": ("fake.png", b"definitely-not-png-bytes", "image/png")},
    )
    assert fake_png.status_code == 422

    # Tamaño mayor a 5 MB -> 413
    oversized = api_client.post(
        "/api/campaigns/watermarks",
        files={
            "file": ("big.png", b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024 + 10), "image/png")
        },
    )
    assert oversized.status_code == 413

    # Path traversal en GET watermark
    traversal = api_client.get("/api/campaigns/watermarks/..%2Fsecret.png")
    assert traversal.status_code in {403, 404}
