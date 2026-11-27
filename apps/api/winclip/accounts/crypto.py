"""Almacenamiento cifrado de credenciales de cuentas sociales (Fernet + Keychain).

Resolución de la clave maestra (`design.md`, decisión 1):
1. `Settings.winclip_secret_key` si está definida en entorno/`.env`.
2. macOS Keychain vía `keyring` (`service="winclip"`, `username="master_key"`).
   Si no existe, se genera una clave Fernet nueva y se guarda automáticamente.

Las credenciales OAuth se guardan en `storage/accounts/<account_id>/credentials.enc`
con permisos `0600`, escritura atómica (temporal + `os.replace`) y nunca se guardan
en SQLite ni se imprimen en logs.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

import keyring
from cryptography.fernet import Fernet, InvalidToken
from keyring.errors import KeyringError

from winclip.core.config import Settings
from winclip.core.ids import validate_project_id
from winclip.core.storage import LocalStorage

KEYRING_SERVICE = "winclip"
KEYRING_USERNAME = "master_key"
ACCOUNTS_DIR = "accounts"
CREDENTIALS_FILENAME = "credentials.enc"
PROFILE_DIRNAME = "profile"


class CryptoError(RuntimeError):
    """Error base al cifrar, descifrar o resolver la clave maestra."""


class KeyResolutionError(CryptoError):
    """No se pudo obtener ni generar la clave maestra de cifrado."""


class CredentialsNotFoundError(CryptoError):
    """El archivo cifrado de credenciales de la cuenta no existe."""


class CredentialDecryptionError(CryptoError):
    """No se pudo descifrar `credentials.enc` (clave distinta o archivo corrupto)."""


@runtime_checkable
class CredentialStore(Protocol):
    """Interfaz desacoplada para almacenamiento de credenciales (local hoy, KMS mañana)."""

    def save_credentials(self, account_id: str, payload: dict[str, Any]) -> str: ...

    def load_credentials(self, account_id: str) -> dict[str, Any]: ...

    def delete_account_dir(self, account_id: str) -> None: ...


def _build_fernet(raw_key: str) -> Fernet:
    key_bytes = raw_key.strip().encode("ascii")
    try:
        return Fernet(key_bytes)
    except (ValueError, TypeError) as exc:
        raise KeyResolutionError(
            "WINCLIP_SECRET_KEY no es una clave Fernet válida (base64 url-safe de 32 bytes)"
        ) from exc


def resolve_master_key(settings: Settings) -> tuple[bytes, Literal["env", "keychain"]]:
    """Obtiene la clave maestra Fernet desde `WINCLIP_SECRET_KEY` o Keychain."""
    env_key = settings.winclip_secret_key.get_secret_value().strip()
    if env_key:
        _build_fernet(env_key)
        return env_key.encode("ascii"), "env"

    try:
        stored = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        if stored:
            _build_fernet(stored)
            return stored.strip().encode("ascii"), "keychain"

        generated = Fernet.generate_key().decode("ascii")
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, generated)
        return generated.encode("ascii"), "keychain"
    except KeyringError as exc:
        raise KeyResolutionError(
            "No se pudo acceder al Keychain del sistema; define WINCLIP_SECRET_KEY en .env"
        ) from exc


def inspect_encryption_backend(settings: Settings) -> tuple[Literal["ok", "warn"], str, str | None]:
    """Inspecciona el backend de cifrado activo para `winclip doctor` sin revelar claves."""
    env_key = settings.winclip_secret_key.get_secret_value().strip()
    if env_key:
        try:
            _build_fernet(env_key)
        except KeyResolutionError:
            return (
                "warn",
                "WINCLIP_SECRET_KEY definida pero con formato inválido",
                "genera una clave Fernet válida con cryptography.fernet.Fernet.generate_key()",
            )
        return ("ok", "backend env (WINCLIP_SECRET_KEY configurada)", None)

    try:
        stored = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except KeyringError as exc:
        return (
            "warn",
            f"Keychain no disponible ({type(exc).__name__})",
            "define WINCLIP_SECRET_KEY en .env si usas WinClip en modo headless",
        )
    if stored:
        return ("ok", "backend keychain (clave maestra presente en Keychain)", None)
    return (
        "ok",
        "backend keychain (se generará clave maestra automáticamente al conectar una cuenta)",
        None,
    )


class LocalCredentialStore:
    """Almacén local de credenciales cifradas y perfiles Playwright bajo `STORAGE_DIR/accounts/`."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._storage = LocalStorage(settings.storage_dir)

    def _fernet(self) -> Fernet:
        key, _backend = resolve_master_key(self._settings)
        return Fernet(key)

    def account_dir(self, account_id: str) -> Path:
        safe_id = validate_project_id(account_id)
        return self._storage.path(ACCOUNTS_DIR, safe_id)

    def credentials_relpath(self, account_id: str) -> str:
        safe_id = validate_project_id(account_id)
        return f"{ACCOUNTS_DIR}/{safe_id}/{CREDENTIALS_FILENAME}"

    def credentials_path(self, account_id: str) -> Path:
        return self.account_dir(account_id) / CREDENTIALS_FILENAME

    def profile_relpath(self, account_id: str) -> str:
        safe_id = validate_project_id(account_id)
        return f"{ACCOUNTS_DIR}/{safe_id}/{PROFILE_DIRNAME}"

    def profile_dir(self, account_id: str) -> Path:
        return self.account_dir(account_id) / PROFILE_DIRNAME

    def ensure_profile_dir(self, account_id: str) -> Path:
        """Crea `storage/accounts/<account_id>/profile/` con permisos `0700`."""
        acc_dir = self.account_dir(account_id)
        acc_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(acc_dir, 0o700)
        prof_dir = acc_dir / PROFILE_DIRNAME
        prof_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(prof_dir, 0o700)
        return prof_dir

    def save_credentials(self, account_id: str, payload: dict[str, Any]) -> str:
        """Cifra `payload` con Fernet y lo escribe atómicamente con permisos `0600`."""
        acc_dir = self.account_dir(account_id)
        acc_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(acc_dir, 0o700)

        target = acc_dir / CREDENTIALS_FILENAME
        plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        token = self._fernet().encrypt(plaintext)

        descriptor, tmp_name = tempfile.mkstemp(
            dir=acc_dir, prefix=f".{CREDENTIALS_FILENAME}.", suffix=".tmp"
        )
        tmp_path = Path(tmp_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(token)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, target)
            os.chmod(target, 0o600)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        return self.credentials_relpath(account_id)

    def load_credentials(self, account_id: str) -> dict[str, Any]:
        """Lee y descifra `credentials.enc` para la cuenta indicada."""
        target = self.credentials_path(account_id)
        if not target.is_file():
            raise CredentialsNotFoundError(
                f"No existen credenciales cifradas para la cuenta {account_id}"
            )
        ciphertext = target.read_bytes()
        try:
            plaintext = self._fernet().decrypt(ciphertext)
        except InvalidToken as exc:
            raise CredentialDecryptionError(
                "Clave de cifrado cambiada o archivo corrupto; reconecta la cuenta"
            ) from exc

        try:
            data = json.loads(plaintext.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CredentialDecryptionError(
                "Credenciales descifradas con formato JSON inválido; reconecta la cuenta"
            ) from exc
        if not isinstance(data, dict):
            raise CredentialDecryptionError("El payload de credenciales debe ser un objeto JSON")
        return data

    def delete_account_dir(self, account_id: str) -> None:
        """Borra `storage/accounts/<account_id>/` completo (credenciales y/o perfil)."""
        acc_dir = self.account_dir(account_id)
        if acc_dir.exists():
            shutil.rmtree(acc_dir, ignore_errors=False)
