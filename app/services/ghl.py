"""Cliente de GoHighLevel (API v2 / LeadConnector).

- Listar custom fields de la location (con su dataType) para elegir uno en Settings.
- Escribir en el contacto cuando ve el vídeo, formateando el valor según el tipo.
"""

from __future__ import annotations

from datetime import date

import httpx

BASE_URL = "https://services.leadconnectorhq.com"
VERSION = "2021-07-28"


class GHLError(Exception):
    pass


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Version": VERSION,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def list_custom_fields(token: str, location_id: str) -> list[dict]:
    """Devuelve [{id, name, dataType, fieldKey}] de los campos de contacto."""
    url = f"{BASE_URL}/locations/{location_id}/customFields"
    try:
        resp = httpx.get(url, headers=_headers(token), params={"model": "contact"}, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as err:
        raise GHLError(f"GHL respondió {err.response.status_code}: {err.response.text[:200]}") from err
    except (httpx.HTTPError, ValueError) as err:
        raise GHLError(f"No se pudo conectar con GHL: {err}") from err

    fields = data.get("customFields") or data.get("custom_fields") or []
    out = []
    for f in fields:
        out.append(
            {
                "id": f.get("id"),
                "name": f.get("name") or f.get("fieldKey") or f.get("id"),
                "dataType": (f.get("dataType") or f.get("type") or "TEXT").upper(),
                "fieldKey": f.get("fieldKey", ""),
            }
        )
    return out


def format_value(data_type: str, override: str = "") -> object:
    """Construye el valor a escribir según el tipo de campo de GHL."""
    dt = (data_type or "TEXT").upper()
    today = date.today().isoformat()
    if dt == "DATE":
        return today
    if dt in ("NUMERICAL", "MONETORY"):
        return 1
    if dt in ("CHECKBOX", "MULTIPLE_OPTIONS"):
        return [override or "Sí"]
    if dt in ("SINGLE_OPTIONS", "RADIO"):
        return override or "Sí"
    return override or f"Visto {today}"


def update_contact_field(
    *,
    token: str,
    contact_id: str,
    field_id: str,
    data_type: str,
    override: str = "",
) -> None:
    """Escribe el valor (según tipo) en el custom field del contacto. Lanza GHLError."""
    value = format_value(data_type, override)
    url = f"{BASE_URL}/contacts/{contact_id}"
    body = {"customFields": [{"id": field_id, "field_value": value}]}
    try:
        resp = httpx.put(url, headers=_headers(token), json=body, timeout=20)
        resp.raise_for_status()
    except httpx.HTTPStatusError as err:
        raise GHLError(
            f"GHL no aceptó la actualización ({err.response.status_code}): {err.response.text[:200]}"
        ) from err
    except httpx.HTTPError as err:
        raise GHLError(f"Fallo escribiendo en GHL: {err}") from err
