"""Ajustes del tenant: setter por defecto, plantilla, conexión GHL y campo destino."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..auth import current_tenant
from ..config import settings
from ..db import get_db
from ..models import Tenant
from ..services import ghl
from ..templating import templates

router = APIRouter(include_in_schema=False)


def _load_fields(tenant: Tenant) -> tuple[list[dict], str | None]:
    if not (tenant.ghl_token and tenant.ghl_location_id):
        return [], None
    try:
        return ghl.list_custom_fields(tenant.ghl_token, tenant.ghl_location_id), None
    except ghl.GHLError as err:
        return [], str(err)


@router.get("/settings")
def settings_page(
    request: Request, tenant: Tenant = Depends(current_tenant)
):
    fields, ghl_error = _load_fields(tenant)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "request": request,
            "tenant": tenant,
            "fields": fields,
            "ghl_error": ghl_error,
            "base_url": settings.base_url,
            "msg": request.query_params.get("msg"),
            "err": request.query_params.get("err"),
        },
    )


@router.post("/settings")
def save_settings(
    request: Request,
    default_setter: str = Form(""),
    message_template: str = Form(""),
    ghl_token: str = Form(""),
    ghl_location_id: str = Form(""),
    ghl_field_id: str = Form(""),
    ghl_field_value: str = Form(""),
    tenant: Tenant = Depends(current_tenant),
    db: Session = Depends(get_db),
):
    tenant.default_setter = default_setter.strip()
    tenant.message_template = message_template.strip() or tenant.message_template
    tenant.ghl_token = ghl_token.strip()
    tenant.ghl_location_id = ghl_location_id.strip()
    tenant.ghl_field_value = ghl_field_value.strip()

    # Resolver nombre + tipo del campo elegido consultando a GHL (type-aware).
    tenant.ghl_field_id = ghl_field_id.strip()
    tenant.ghl_field_name = ""
    tenant.ghl_field_type = ""
    if tenant.ghl_field_id:
        fields, _ = _load_fields(tenant)
        for f in fields:
            if f["id"] == tenant.ghl_field_id:
                tenant.ghl_field_name = f["name"]
                tenant.ghl_field_type = f["dataType"]
                break

    db.commit()
    return RedirectResponse("/settings?msg=Ajustes guardados.", status_code=303)
