"""`/api/campaigns`: CRUD, duplicación, plantillas ES/EN, parseo IA y subida de watermark."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from winclip.core.db import ensure_default_workspace
from winclip.core.ids import new_ulid
from winclip.core.models import Campaign, utcnow
from winclip.core.storage import LocalStorage, StoragePathError
from winclip.routers.deps import SessionDep, SettingsDep
from winclip.routers.schemas import (
    CampaignCreate,
    CampaignOut,
    CampaignParseOut,
    CampaignParseRequest,
    CampaignTemplateOut,
    CampaignUpdate,
    WatermarkUploadOut,
)
from winclip.routers.serializers import campaign_out
from winclip.rules.parser import BriefParseError, parse_campaign_brief
from winclip.rules.schema import CampaignRules, load_campaign_templates

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

MAX_WATERMARK_BYTES = 5 * 1024 * 1024
ALLOWED_WATERMARK_MIME = frozenset({"image/png", "image/webp"})
_WATERMARK_FILENAME_RE = re.compile(r"^[a-z0-9_-]+\.(?:png|webp)$")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _campaign_or_404(session: Session, campaign_id: str) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"no existe la campaña {campaign_id}",
        )
    return campaign


def _detect_image_extension(data: bytes) -> str | None:
    if data.startswith(_PNG_SIGNATURE):
        return "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _duplicate_name(base_name: str) -> str:
    suffix = " (copia)"
    max_base = 120 - len(suffix)
    return f"{base_name[:max_base].rstrip()}{suffix}"


@router.get("", response_model=list[CampaignOut], operation_id="listCampaigns")
def list_campaigns(session: SessionDep) -> list[CampaignOut]:
    """Lista las campañas del workspace ordenadas por última actualización."""
    campaigns = session.exec(
        select(Campaign).order_by(Campaign.updated_at.desc(), Campaign.id.desc())
    ).all()
    return [campaign_out(session, item) for item in campaigns]


@router.get(
    "/templates",
    response_model=list[CampaignTemplateOut],
    operation_id="listCampaignTemplates",
)
def list_campaign_templates() -> list[CampaignTemplateOut]:
    """Plantillas predefinidas ES/EN listas para precargar en el editor."""
    return [
        CampaignTemplateOut(
            id=tpl.id,
            title=tpl.title,
            description=tpl.description,
            language=tpl.language,
            rules=tpl.rules,
        )
        for tpl in load_campaign_templates()
    ]


@router.post(
    "/parse",
    response_model=CampaignParseOut,
    operation_id="parseCampaignBrief",
)
def parse_brief(payload: CampaignParseRequest, settings: SettingsDep) -> CampaignParseOut:
    """Convierte un brief en texto libre en una propuesta de reglas sin persistir."""
    try:
        draft = parse_campaign_brief(payload.source_text, settings=settings)
    except BriefParseError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return CampaignParseOut(
        rules=draft.rules,
        inferred_fields=draft.inferred_fields,
        warnings=draft.warnings,
        provider=draft.provider,
    )


@router.post(
    "/watermarks",
    response_model=WatermarkUploadOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="uploadCampaignWatermark",
)
async def upload_watermark(
    settings: SettingsDep,
    file: Annotated[UploadFile, File(...)],
) -> WatermarkUploadOut:
    """Sube una imagen PNG o WebP (máx. 5 MB) bajo `storage/campaigns/watermarks/`."""
    content_type = (file.content_type or "").lower().split(";")[0].strip()
    if content_type and content_type not in ALLOWED_WATERMARK_MIME:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"formato de marca de agua no permitido ({content_type}); usa PNG o WebP",
        )

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_WATERMARK_BYTES:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                "la marca de agua supera el límite de 5 MB",
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "el archivo de marca de agua está vacío",
        )

    ext = _detect_image_extension(data)
    if ext is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "el archivo no es una imagen PNG o WebP válida",
        )

    storage = LocalStorage(settings.storage_dir)
    filename = f"{new_ulid()}.{ext}"
    relative = f"campaigns/watermarks/{filename}"
    target: Path = storage.resolve_safe(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return WatermarkUploadOut(watermark_path=relative)


@router.get(
    "/watermarks/{filename}",
    operation_id="getCampaignWatermark",
)
def get_watermark(filename: str, settings: SettingsDep) -> FileResponse:
    """Sirve una imagen de marca de agua previamente subida."""
    if not _WATERMARK_FILENAME_RE.fullmatch(filename):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "nombre de marca de agua no permitido")
    storage = LocalStorage(settings.storage_dir)
    try:
        path = storage.resolve_safe(f"campaigns/watermarks/{filename}")
    except StoragePathError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "ruta de marca de agua no permitida"
        ) from exc
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "la marca de agua no existe")
    media_type = "image/png" if filename.endswith(".png") else "image/webp"
    return FileResponse(path, media_type=media_type)


@router.post(
    "",
    response_model=CampaignOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="createCampaign",
)
def create_campaign(payload: CampaignCreate, session: SessionDep) -> CampaignOut:
    """Crea una campaña persistida en SQLite para el workspace activo."""
    workspace = ensure_default_workspace(session)
    normalized_rules = payload.rules.model_copy(update={"name": payload.name})
    CampaignRules.model_validate(normalized_rules.model_dump(mode="json"))

    now = utcnow()
    campaign = Campaign(
        id=new_ulid(),
        workspace_id=workspace.id,
        name=payload.name,
        rules_json=normalized_rules.model_dump(mode="json"),
        source_text=payload.source_text,
        created_at=now,
        updated_at=now,
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign_out(session, campaign)


@router.get("/{campaign_id}", response_model=CampaignOut, operation_id="getCampaign")
def get_campaign(campaign_id: str, session: SessionDep) -> CampaignOut:
    """Devuelve el detalle de una campaña."""
    return campaign_out(session, _campaign_or_404(session, campaign_id))


@router.patch("/{campaign_id}", response_model=CampaignOut, operation_id="updateCampaign")
def update_campaign(
    campaign_id: str,
    payload: CampaignUpdate,
    session: SessionDep,
) -> CampaignOut:
    """Actualiza parcialmente nombre, reglas y/o texto fuente de una campaña."""
    campaign = _campaign_or_404(session, campaign_id)
    changes = payload.model_dump(exclude_unset=True)

    current_rules = CampaignRules.model_validate(campaign.rules_json)
    next_name = changes.get("name") or campaign.name
    next_rules = payload.rules if payload.rules is not None else current_rules
    if "name" not in changes and payload.rules is not None:
        next_name = payload.rules.name
    synced_rules = next_rules.model_copy(update={"name": next_name})
    CampaignRules.model_validate(synced_rules.model_dump(mode="json"))

    campaign.name = next_name
    campaign.rules_json = synced_rules.model_dump(mode="json")
    if "source_text" in changes:
        campaign.source_text = payload.source_text
    campaign.updated_at = utcnow()
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign_out(session, campaign)


@router.delete(
    "/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteCampaign",
)
def delete_campaign(campaign_id: str, session: SessionDep) -> None:
    """Elimina la campaña; los proyectos asociados conservan sus clips con `campaign_id = null`."""
    campaign = _campaign_or_404(session, campaign_id)
    session.delete(campaign)
    session.commit()
    return None


@router.post(
    "/{campaign_id}/duplicate",
    response_model=CampaignOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="duplicateCampaign",
)
def duplicate_campaign(campaign_id: str, session: SessionDep) -> CampaignOut:
    """Clona una campaña independiente con nuevo ULID y nombre `<name> (copia)`."""
    source = _campaign_or_404(session, campaign_id)
    copy_name = _duplicate_name(source.name)
    source_rules = CampaignRules.model_validate(source.rules_json)
    cloned_rules = source_rules.model_copy(update={"name": copy_name})

    now = utcnow()
    duplicate = Campaign(
        id=new_ulid(),
        workspace_id=source.workspace_id,
        name=copy_name,
        rules_json=cloned_rules.model_dump(mode="json"),
        source_text=source.source_text,
        created_at=now,
        updated_at=now,
    )
    session.add(duplicate)
    session.commit()
    session.refresh(duplicate)
    return campaign_out(session, duplicate)
