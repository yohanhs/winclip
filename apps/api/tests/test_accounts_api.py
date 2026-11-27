"""Tests de la API `/api/accounts`, CLI `winclip accounts`, doctor y cero fuga de secretos."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlmodel import Session
from typer.testing import CliRunner

from winclip.accounts.browser_login import BrowserLoginSession
from winclip.accounts.crypto import LocalCredentialStore
from winclip.accounts.logging_filter import redact_secrets
from winclip.accounts.oauth import InstagramCandidate, get_oauth_state_manager
from winclip.cli import app as cli_app
from winclip.core.config import Settings
from winclip.core.db import clear_engine_cache, ensure_default_workspace, init_db
from winclip.core.doctor import run_checks
from winclip.core.ids import new_ulid
from winclip.core.models import SocialAccount
from winclip.main import create_app


def _make_settings(tmp_path: Path) -> Settings:
    secret_file = tmp_path / "google_client_fixture.json"
    secret_file.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "fake-google-cid-test",
                    "client_secret": "fake-google-secret-value-999",
                }
            }
        ),
        encoding="utf-8",
    )
    return Settings(
        storage_dir=tmp_path / "storage",
        winclip_secret_key=SecretStr(Fernet.generate_key().decode("ascii")),
        google_client_secret_file=str(secret_file),
        tiktok_client_key=SecretStr("fake-tiktok-key-value-999"),
        tiktok_client_secret=SecretStr("fake-tiktok-secret-value-999"),
        meta_app_id="fake-meta-app-id-test",
        meta_app_secret=SecretStr("fake-meta-secret-value-999"),
    )


def test_accounts_crud_default_switch_and_zero_secret_leak(tmp_path: Path, caplog) -> None:
    clear_engine_cache()
    settings = _make_settings(tmp_path)
    app = create_app(settings)

    secret_token = "fake-super-secret-access-token-test"
    refresh_token = "fake-super-secret-refresh-token-test"

    with TestClient(app) as client:
        store = LocalCredentialStore(settings)
        with Session(app.state.engine) as session:
            ws = ensure_default_workspace(session)
            id1 = new_ulid()
            id2 = new_ulid()
            ref1 = store.save_credentials(
                id1, {"access_token": secret_token, "refresh_token": refresh_token}
            )
            ref2 = store.save_credentials(
                id2, {"access_token": "fake-second-token-test", "refresh_token": "fake-ref-2"}
            )
            session.add(
                SocialAccount(
                    id=id1,
                    workspace_id=ws.id,
                    platform="youtube",
                    display_name="HookVault",
                    handle="@hookvault",
                    auth_method="api",
                    credentials_ref=ref1,
                    status="connected",
                    is_default=True,
                    capabilities_json={"direct_post": True},
                )
            )
            session.add(
                SocialAccount(
                    id=id2,
                    workspace_id=ws.id,
                    platform="youtube",
                    display_name="Canal Dos",
                    handle="@canaldos",
                    auth_method="api",
                    credentials_ref=ref2,
                    status="connected",
                    is_default=False,
                )
            )
            session.commit()

        with caplog.at_level(logging.DEBUG):
            list_resp = client.get("/api/accounts")
            assert list_resp.status_code == 200
            raw_body = list_resp.text
            assert secret_token not in raw_body
            assert refresh_token not in raw_body
            assert "credentials.enc" not in raw_body
            assert "fake-google-secret-value-999" not in raw_body

            items = list_resp.json()
            assert len(items) == 2

            # Renombrar alias y cambiar default a la segunda cuenta
            patch_resp = client.patch(
                f"/api/accounts/{id2}",
                json={"alias": "Secundario", "is_default": True},
            )
            assert patch_resp.status_code == 200
            assert patch_resp.json()["alias"] == "Secundario"
            assert patch_resp.json()["is_default"] is True

            # Verificar que la primera dejó de ser default
            items_after = {item["id"]: item for item in client.get("/api/accounts").json()}
            assert items_after[id1]["is_default"] is False
            assert items_after[id2]["is_default"] is True

            # Eliminar cuenta 1 borra el registro y el directorio en disco
            del_resp = client.delete(f"/api/accounts/{id1}")
            assert del_resp.status_code == 204
            assert not store.account_dir(id1).exists()

        # Ningún log debe contener tokens ni secretos
        all_logs = "\n".join(rec.getMessage() for rec in caplog.records)
        assert secret_token not in all_logs
        assert refresh_token not in all_logs
        assert "fake-google-secret-value-999" not in all_logs


def test_accounts_oauth_config_start_and_instagram_select(tmp_path: Path) -> None:
    clear_engine_cache()
    settings = _make_settings(tmp_path)
    app = create_app(settings)

    with TestClient(app) as client:
        cfg_resp = client.get("/api/accounts/config")
        assert cfg_resp.status_code == 200
        assert "fake-tiktok-secret-value-999" not in cfg_resp.text
        platforms = {p["platform"]: p for p in cfg_resp.json()["platforms"]}
        assert platforms["youtube"]["configured"] is True
        assert platforms["tiktok"]["configured"] is True
        assert platforms["instagram"]["configured"] is True

        start_resp = client.post("/api/accounts/oauth/youtube/start", json={"alias": "Main"})
        assert start_resp.status_code == 200
        assert "accounts.google.com" in start_resp.json()["auth_url"]

        # Simular callback con múltiples cuentas IG pendientes
        mgr = get_oauth_state_manager()
        pending = mgr.create_ig_selection(
            workspace_id="ws",
            user_access_token="fake-ig-token-test",
            token_expires_at=None,
            candidates=[
                InstagramCandidate(
                    external_account_id="ig_1",
                    username="brand_one",
                    display_name="Brand One",
                    avatar_url=None,
                    page_id="p1",
                    page_name="Brand Page",
                    page_access_token="fake-page-tok",
                )
            ],
        )
        with Session(app.state.engine) as session:
            pending.workspace_id = ensure_default_workspace(session).id

        pend_resp = client.get(f"/api/accounts/oauth/instagram/pending/{pending.token}")
        assert pend_resp.status_code == 200
        assert "fake-ig-token-test" not in pend_resp.text
        assert len(pend_resp.json()["candidates"]) == 1

        sel_resp = client.post(
            "/api/accounts/oauth/instagram/select",
            json={"selection_token": pending.token, "external_account_ids": ["ig_1"]},
        )
        assert sel_resp.status_code == 200
        assert sel_resp.json()[0]["handle"] == "@brand_one"


def test_accounts_browser_login_and_import_endpoints(tmp_path: Path) -> None:
    clear_engine_cache()
    settings = _make_settings(tmp_path)
    app = create_app(settings)

    token_file = tmp_path / "fixture_yt_token.json"
    token_file.write_text(
        json.dumps(
            {
                "type": "authorized_user",
                "token": "fake-import-access-test",
                "refresh_token": "fake-import-refresh-test",
                "client_id": "fake-cid",
                "client_secret": "fake-csecret",
            }
        ),
        encoding="utf-8",
    )

    with TestClient(app) as client:
        with patch("winclip.accounts.importer.check_account", side_effect=lambda s, a, cfg, **k: a):
            imp_resp = client.post(
                "/api/accounts/import",
                json={"path": str(token_file), "alias": "Importada"},
            )
        assert imp_resp.status_code == 201
        assert "fake-import-refresh-test" not in imp_resp.text
        assert imp_resp.json()[0]["alias"] == "Importada"

        fake_sess = BrowserLoginSession(account_id="temp", platform="tiktok", status="waiting")
        with (
            patch(
                "winclip.accounts.browser_login.BrowserLoginManager.start_login",
                return_value=fake_sess,
            ),
            patch(
                "winclip.accounts.browser_login.BrowserLoginManager.get_session",
                return_value=fake_sess,
            ),
            patch(
                "winclip.accounts.browser_login.BrowserLoginManager.confirm_login",
                return_value=fake_sess,
            ),
        ):
            start_b = client.post(
                "/api/accounts/browser-login/start",
                json={"platform": "tiktok", "alias": "TT Web"},
            )
            assert start_b.status_code == 200
            acc_id = start_b.json()["account_id"]

            stat_b = client.get(f"/api/accounts/{acc_id}/browser-login/status")
            assert stat_b.status_code == 200
            assert stat_b.json()["session_status"] == "waiting"

            conf_b = client.post(f"/api/accounts/{acc_id}/browser-login/confirm")
            assert conf_b.status_code == 200


def test_doctor_and_cli_accounts_never_leak_secrets(tmp_path: Path) -> None:
    clear_engine_cache()
    settings = _make_settings(tmp_path)
    init_db(settings)

    results = run_checks(settings)
    serialized = json.dumps([r.to_dict() for r in results])
    assert "fake-tiktok-secret-value-999" not in serialized
    assert "fake-meta-secret-value-999" not in serialized
    assert "fake-google-secret-value-999" not in serialized
    names = {r.name for r in results}
    assert {"cifrado cuentas", "GOOGLE_CLIENT_SECRET_FILE", "TIKTOK_OAUTH", "META_OAUTH"} <= names

    runner = CliRunner()
    with patch("winclip.cli.get_settings", return_value=settings):
        res_list = runner.invoke(cli_app, ["accounts", "list"])
        assert res_list.exit_code == 0

    assert "[REDACTED]" in redact_secrets("Authorization: Bearer fake-token-123")
    assert "fake-token-123" not in redact_secrets("access_token=fake-token-123&other=1")
