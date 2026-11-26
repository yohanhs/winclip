"""Configuración central del backend (variables de `docs/architecture.md §4`).

Toda la configuración se lee de variables de entorno o del `.env` de la raíz del repo.
Ninguna clave es obligatoria: la API arranca sin claves de LLM y el doctor las marca
como "ausente".
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del repo: apps/api/winclip/core/config.py -> core -> winclip -> api -> apps -> repo
ROOT_DIR = Path(__file__).resolve().parents[4]
ENV_FILE = ROOT_DIR / ".env"

DEFAULT_FFMPEG_BIN = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
DEFAULT_FFPROBE_BIN = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffprobe")


class Settings(BaseSettings):
    """Ajustes de WinClip, sobrescribibles por entorno o `.env`."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Marca y puertos
    app_name: str = "WinClip"
    api_port: int = 8000
    web_port: int = 3000

    # Almacenamiento
    storage_dir: Path = Path("./storage")
    database_url: str | None = None

    # Herramientas locales (ffmpeg-full es keg-only: nunca usar el ffmpeg del PATH)
    ffmpeg_bin: Path = DEFAULT_FFMPEG_BIN
    ffprobe_bin: Path = DEFAULT_FFPROBE_BIN
    ytdlp_bin: str = "yt-dlp"

    # Transcripción
    whisper_model: str = "mlx-community/whisper-large-v3-turbo"

    # LLM (gratuitos, con router y fallback)
    gemini_api_key: SecretStr = SecretStr("")
    nvidia_api_key: SecretStr = SecretStr("")
    openrouter_api_key: SecretStr = SecretStr("")
    groq_api_key: SecretStr = SecretStr("")
    llm_provider_order: str = "gemini,nvidia,openrouter,groq,ollama"
    ollama_host: str = "http://localhost:11434"

    # Cuentas y cifrado
    google_client_secret_file: str = ""
    tiktok_client_key: SecretStr = SecretStr("")
    tiktok_client_secret: SecretStr = SecretStr("")
    meta_app_id: str = ""
    meta_app_secret: SecretStr = SecretStr("")
    winclip_secret_key: SecretStr = SecretStr("")

    # Fuentes locales no redistribuibles
    user_fonts_dir: Path = Path("~/Library/Fonts")

    @field_validator("storage_dir")
    @classmethod
    def _resolve_storage_dir(cls, value: Path) -> Path:
        """Las rutas relativas se resuelven contra la raíz del repo, no contra el cwd."""
        value = value.expanduser()
        return value if value.is_absolute() else (ROOT_DIR / value).resolve()

    @field_validator("ffmpeg_bin", "ffprobe_bin", "user_fonts_dir")
    @classmethod
    def _expand_path(cls, value: Path) -> Path:
        return value.expanduser()

    @model_validator(mode="after")
    def _derive_database_url(self) -> Settings:
        if not self.database_url:
            db_path = self.storage_dir / "winclip.db"
            self.database_url = f"sqlite:///{db_path}"
        return self

    @property
    def llm_providers(self) -> list[str]:
        """Orden de proveedores LLM configurado."""
        return [name.strip() for name in self.llm_provider_order.split(",") if name.strip()]

    @property
    def api_key_presence(self) -> dict[str, bool]:
        """Presencia de cada clave, sin exponer nunca su valor."""
        keys: dict[str, SecretStr] = {
            "GEMINI_API_KEY": self.gemini_api_key,
            "NVIDIA_API_KEY": self.nvidia_api_key,
            "OPENROUTER_API_KEY": self.openrouter_api_key,
            "GROQ_API_KEY": self.groq_api_key,
            "TIKTOK_CLIENT_KEY": self.tiktok_client_key,
            "TIKTOK_CLIENT_SECRET": self.tiktok_client_secret,
            "META_APP_SECRET": self.meta_app_secret,
        }
        return {name: bool(secret.get_secret_value().strip()) for name, secret in keys.items()}


@lru_cache
def get_settings() -> Settings:
    """Ajustes cacheados para la API y la CLI."""
    return Settings()
