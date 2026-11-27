"""Tests unitarios de `winclip/accounts/crypto.py` (Fernet + Keychain + permisos)."""

from __future__ import annotations

import stat
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from winclip.accounts.crypto import (
    CredentialDecryptionError,
    CredentialsNotFoundError,
    KeyResolutionError,
    LocalCredentialStore,
    inspect_encryption_backend,
    resolve_master_key,
)
from winclip.core.config import Settings
from winclip.core.ids import new_ulid


def _settings(tmp_path: Path, secret_key: str = "") -> Settings:
    return Settings(
        storage_dir=tmp_path,
        winclip_secret_key=SecretStr(secret_key),
    )


def test_encrypt_decrypt_roundtrip_and_file_permissions(tmp_path: Path) -> None:
    key = Fernet.generate_key().decode("ascii")
    store = LocalCredentialStore(_settings(tmp_path, secret_key=key))
    account_id = new_ulid()
    payload = {
        "access_token": "fake-access-token-test",
        "refresh_token": "fake-refresh-token-test",
        "scope": "youtube.upload",
    }

    relpath = store.save_credentials(account_id, payload)
    assert relpath == f"accounts/{account_id}/credentials.enc"

    enc_path = store.credentials_path(account_id)
    assert enc_path.is_file()
    mode = stat.S_IMODE(enc_path.stat().st_mode)
    assert mode == 0o600

    # El archivo en disco nunca debe contener el token en claro
    raw_bytes = enc_path.read_bytes()
    assert b"fake-access-token-test" not in raw_bytes
    assert b"fake-refresh-token-test" not in raw_bytes

    loaded = store.load_credentials(account_id)
    assert loaded == payload


def test_decrypt_with_different_key_raises_controlled_error(tmp_path: Path) -> None:
    key1 = Fernet.generate_key().decode("ascii")
    key2 = Fernet.generate_key().decode("ascii")
    account_id = new_ulid()

    store1 = LocalCredentialStore(_settings(tmp_path, secret_key=key1))
    store1.save_credentials(account_id, {"access_token": "fake-access-token-test"})

    store2 = LocalCredentialStore(_settings(tmp_path, secret_key=key2))
    with pytest.raises(CredentialDecryptionError, match="Clave de cifrado cambiada"):
        store2.load_credentials(account_id)


def test_load_missing_credentials_raises_not_found(tmp_path: Path) -> None:
    key = Fernet.generate_key().decode("ascii")
    store = LocalCredentialStore(_settings(tmp_path, secret_key=key))
    with pytest.raises(CredentialsNotFoundError):
        store.load_credentials(new_ulid())


def test_delete_account_dir_removes_credentials_and_profile(tmp_path: Path) -> None:
    key = Fernet.generate_key().decode("ascii")
    store = LocalCredentialStore(_settings(tmp_path, secret_key=key))
    account_id = new_ulid()

    store.save_credentials(account_id, {"access_token": "fake-access-token-test"})
    profile = store.ensure_profile_dir(account_id)
    (profile / "Cookies").write_text("dummy", encoding="utf-8")
    assert stat.S_IMODE(profile.stat().st_mode) == 0o700

    store.delete_account_dir(account_id)
    assert not store.account_dir(account_id).exists()


def test_resolve_master_key_falls_back_to_keyring_and_generates(tmp_path: Path) -> None:
    settings = _settings(tmp_path, secret_key="")
    vault: dict[tuple[str, str], str] = {}

    def fake_get(service: str, username: str) -> str | None:
        return vault.get((service, username))

    def fake_set(service: str, username: str, value: str) -> None:
        vault[(service, username)] = value

    with (
        patch("winclip.accounts.crypto.keyring.get_password", side_effect=fake_get),
        patch("winclip.accounts.crypto.keyring.set_password", side_effect=fake_set),
    ):
        key1, backend1 = resolve_master_key(settings)
        assert backend1 == "keychain"
        assert ("winclip", "master_key") in vault

        key2, backend2 = resolve_master_key(settings)
        assert backend2 == "keychain"
        assert key1 == key2


def test_invalid_env_secret_key_raises_and_doctor_warns(tmp_path: Path) -> None:
    settings = _settings(tmp_path, secret_key="not-a-valid-fernet-key")
    with pytest.raises(KeyResolutionError):
        resolve_master_key(settings)

    status, detail, hint = inspect_encryption_backend(settings)
    assert status == "warn"
    assert "not-a-valid-fernet-key" not in detail
    assert hint is not None
