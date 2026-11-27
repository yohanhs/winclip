"""Filtro de sanitización de logs para garantizar cero fugas de tokens o secretos."""

from __future__ import annotations

import logging
import re

_SECRET_PATTERNS = (
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-~+/]+=*", re.IGNORECASE),
    re.compile(
        r"((?:access_token|refresh_token|client_secret|page_access_token|fb_exchange_token|winclip_secret_key)\s*[=:]\s*['\"]?)([^'\"\s,&}]+)",
        re.IGNORECASE,
    ),
)


def redact_secrets(text: str) -> str:
    """Enmascara tokens y secretos conocidos antes de escribir en logs."""
    result = text
    result = _SECRET_PATTERNS[0].sub(r"\1[REDACTED]", result)
    result = _SECRET_PATTERNS[1].sub(r"\1[REDACTED]", result)
    return result


class SecretRedactionFilter(logging.Filter):
    """Filtro `logging.Filter` que redacta credenciales en mensajes y argumentos."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    redact_secrets(a) if isinstance(a, str) else a for a in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    k: redact_secrets(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
        return True


def install_accounts_log_filter() -> None:
    """Instala el filtro de sanitización en el logger `winclip.accounts` (idempotente)."""
    logger = logging.getLogger("winclip.accounts")
    if not any(isinstance(f, SecretRedactionFilter) for f in logger.filters):
        logger.addFilter(SecretRedactionFilter())
