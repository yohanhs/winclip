"""Tests de `winclip/accounts/importer.py` usando exclusivamente fixtures temporales ficticias."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlmodel import Session, select

from winclip.accounts.crypto import LocalCredentialStore
from winclip.accounts.importer import TokenImportError, import_local_tokens
from winclip.core.config import Settings
from winclip.core.db import clear_engine_cache, init_db
from winclip.core.models import SocialAccount


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        storage_dir=tmp_path / "storage",
        winclip_secret_key=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def test_import_google_authorized_user_token_readonly(tmp_path: Path) -> None:
    clear_engine_cache()
    settings = _settings(tmp_path)
    engine = init_db(settings)

    token_file = tmp_path / "external_tokens" / "hookvault_yt.json"
    token_file.parent.mkdir(parents=True)
    original_content = json.dumps(
        {
            "type": "authorized_user",
            "token": "fake-access-token-test",
            "refresh_token": "fake-refresh-token-test",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "fake-client-id-test",
            "client_secret": "fake-client-secret-test",
            "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
        },
        indent=2,
    )
    token_file.write_text(original_content, encoding="utf-8")
    mtime_before = token_file.stat().st_mtime_ns

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "UC_IMP_1",
                        "snippet": {
                            "title": "HookVault Imported",
                            "customUrl": "@hookvault",
                        },
                    }
                ]
            },
        )

    with Session(engine) as session:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            accounts = import_local_tokens(
                session,
                settings,
                token_file,
                alias="Principal YT",
                run_health_check=True,
                http_client=client,
            )

        assert len(accounts) == 1
        acc = accounts[0]
        assert acc.platform == "youtube"
        assert acc.display_name == "HookVault Imported"
        assert acc.handle == "@hookvault"
        assert acc.alias == "Principal YT"
        assert acc.status == "connected"

        # El archivo origen permanece intacto
        assert token_file.read_text(encoding="utf-8") == original_content
        assert token_file.stat().st_mtime_ns == mtime_before

        # En disco está cifrado en storage/accounts/<id>/credentials.enc
        store = LocalCredentialStore(settings)
        enc_bytes = store.credentials_path(acc.id).read_bytes()
        assert b"fake-refresh-token-test" not in enc_bytes
        loaded = store.load_credentials(acc.id)
        assert loaded["refresh_token"] == "fake-refresh-token-test"


def test_import_directory_of_tokens_detects_youtube_and_tiktok(tmp_path: Path) -> None:
    clear_engine_cache()
    settings = _settings(tmp_path)
    engine = init_db(settings)

    tokens_dir = tmp_path / "tokens_dir"
    tokens_dir.mkdir()
    (tokens_dir / "a_youtube.json").write_text(
        json.dumps(
            {
                "refresh_token": "fake-yt-refresh-test",
                "client_id": "fake-cid-test",
                "client_secret": "fake-csecret-test",
            }
        ),
        encoding="utf-8",
    )
    (tokens_dir / "b_tiktok.json").write_text(
        json.dumps(
            {
                "access_token": "fake-tt-access-test",
                "refresh_token": "fake-tt-refresh-test",
                "open_id": "fake-open-id-test",
                "scope": "user.info.basic,video.upload",
            }
        ),
        encoding="utf-8",
    )

    with Session(engine) as session:
        accounts = import_local_tokens(session, settings, tokens_dir, run_health_check=False)
        assert len(accounts) == 2
        platforms = {a.platform for a in accounts}
        assert platforms == {"youtube", "tiktok"}


def test_import_missing_or_invalid_file_creates_no_orphans(tmp_path: Path) -> None:
    clear_engine_cache()
    settings = _settings(tmp_path)
    engine = init_db(settings)

    bad_file = tmp_path / "invalid.json"
    bad_file.write_text(json.dumps({"hello": "world"}), encoding="utf-8")

    with Session(engine) as session:
        with pytest.raises(TokenImportError, match="no existe"):
            import_local_tokens(session, settings, tmp_path / "does_not_exist.json")

        with pytest.raises(TokenImportError, match="formato de token soportado"):
            import_local_tokens(session, settings, bad_file)

        assert session.exec(select(SocialAccount)).all() == []
