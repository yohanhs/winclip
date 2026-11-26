"""`GET /api/health`: diagnóstico del sistema para la CLI y la web."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from winclip.core.doctor import health_payload

router = APIRouter(tags=["health"])


class CheckOut(BaseModel):
    name: str
    status: Literal["ok", "warn", "error"]
    detail: str
    hint: str | None = None


class HealthOut(BaseModel):
    app: str
    version: str
    checks: list[CheckOut]


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(**health_payload())  # type: ignore[arg-type]
