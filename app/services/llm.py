"""Cliente de DeepInfra (DeepSeek) para clasificar vídeos y elegir el mejor para un lead.

Endpoint compatible con OpenAI: {base_url}/chat/completions.
Si no hay API key configurada, funciona en MODO DEMO (mock determinista) para
que todo el flujo sea usable sin gastar tokens.
"""

from __future__ import annotations

import json
import re

import httpx

from ..config import settings

# ── Prompts ─────────────────────────────────────────────────────────────────

_CLASSIFY_SYSTEM = """Eres un estratega comercial B2B. Analizas vídeos de venta y los clasificas \
para una biblioteca de activos comerciales. Respondes SIEMPRE en español y SOLO con JSON válido.

Devuelve un objeto con esta forma exacta:
{
  "summary": "resumen comercial en 2-3 frases: para quién es y qué problema resuelve",
  "stage": "pre-call" | "post-call" | "nurturing" | "reactivación",
  "pain_category": "el dolor principal (texto corto)",
  "use_case": "cuándo y a quién mandar este vídeo (1-2 frases)",
  "tags": [
     {"name": "...", "type": "dolor"|"fase"|"objecion", "confidence": 0.0-1.0}
  ]
}
Para 'tags' usa preferentemente las etiquetas del vocabulario que te paso; puedes proponer \
nuevas si encajan mejor. No inventes datos que no estén en el vídeo."""

_RECOMMEND_SYSTEM = """Eres un sistema de "prescripción de contenido comercial": dado el \
diagnóstico de un lead, eliges de una biblioteca el vídeo que mejor ataca su dolor y redactas \
un mensaje corto y personalizado para acompañarlo. Respondes SIEMPRE en español y SOLO con \
JSON válido.

Devuelve:
{
  "video_id": <id entero del vídeo elegido>,
  "reasoning": "por qué este vídeo encaja con el dolor del lead (1-2 frases)",
  "confidence": 0.0-1.0,
  "alternatives": [<ids de 0-2 vídeos alternativos>]
}
Elige SOLO entre los vídeos que te paso. Si ninguno encaja bien, devuelve el más cercano con \
confidence baja."""


# ── Cliente HTTP a DeepInfra ─────────────────────────────────────────────────


class LLMError(Exception):
    pass


def _chat(system: str, user: str, *, temperature: float = 0.3, max_tokens: int = 1200) -> dict:
    """Llama al endpoint compatible OpenAI de DeepInfra y devuelve JSON parseado."""
    url = f"{settings.deepinfra_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.deepinfra_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.deepinfra_api_key}",
        "Content-Type": "application/json",
    }
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=settings.request_timeout)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as err:
        raise LLMError(f"DeepInfra respondió {err.response.status_code}: {err.response.text[:300]}") from err
    except (httpx.HTTPError, KeyError, IndexError) as err:
        raise LLMError(f"Fallo llamando a DeepInfra: {err}") from err
    return _parse_json(content)


def _parse_json(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Algunos modelos envuelven el JSON en ```json ... ``` o texto extra.
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        raise LLMError("La respuesta del modelo no es JSON válido.")


# ── Funciones públicas ───────────────────────────────────────────────────────


def classify_video(
    *, title: str, description: str, transcript: str | None, tag_vocabulary: list[str]
) -> dict:
    """Clasifica un vídeo. Devuelve dict con summary, stage, pain_category, use_case, tags."""
    if not settings.llm_enabled:
        return _mock_classify(title, description)

    body = transcript[:8000] if transcript else "(sin transcripción; usa título y descripción)"
    user = (
        f"VOCABULARIO DE ETIQUETAS DISPONIBLES:\n{', '.join(tag_vocabulary)}\n\n"
        f"TÍTULO:\n{title}\n\n"
        f"DESCRIPCIÓN:\n{description[:2000]}\n\n"
        f"TRANSCRIPCIÓN (puede estar recortada):\n{body}"
    )
    data = _chat(_CLASSIFY_SYSTEM, user)
    return _normalize_classification(data)


def recommend_video(*, lead_context: str, candidates: list[dict]) -> dict:
    """Elige el mejor vídeo para el dolor del lead entre los candidatos activos."""
    if not candidates:
        raise LLMError("No hay vídeos activos en la biblioteca para recomendar.")
    if not settings.llm_enabled:
        return _mock_recommend(lead_context, candidates)

    lines = []
    for c in candidates:
        tags = ", ".join(c.get("tags", [])) or "—"
        lines.append(
            f"- id={c['id']} | título: {c['title']}\n"
            f"  resumen: {c.get('summary') or '—'}\n"
            f"  fase: {c.get('stage') or '—'} | dolor: {c.get('pain_category') or '—'} | tags: {tags}"
        )
    user = (
        f"DIAGNÓSTICO DEL LEAD:\n{lead_context}\n\n"
        f"BIBLIOTECA DE VÍDEOS DISPONIBLES:\n" + "\n".join(lines)
    )
    data = _chat(_RECOMMEND_SYSTEM, user, temperature=0.5)
    return _normalize_recommendation(data, candidates)


# ── Normalización ────────────────────────────────────────────────────────────


def _normalize_classification(data: dict) -> dict:
    tags = []
    for t in data.get("tags", []) or []:
        name = str(t.get("name", "")).strip()
        ttype = str(t.get("type", "")).strip().lower()
        if not name or ttype not in ("dolor", "fase", "objecion"):
            continue
        try:
            conf = float(t.get("confidence", 0.7))
        except (TypeError, ValueError):
            conf = 0.7
        tags.append({"name": name, "type": ttype, "confidence": max(0.0, min(conf, 1.0))})
    return {
        "summary": str(data.get("summary", "")).strip(),
        "stage": (str(data.get("stage")).strip() if data.get("stage") else None),
        "pain_category": (str(data.get("pain_category")).strip() if data.get("pain_category") else None),
        "use_case": str(data.get("use_case", "")).strip(),
        "tags": tags,
    }


def _normalize_recommendation(data: dict, candidates: list[dict]) -> dict:
    valid_ids = {c["id"] for c in candidates}
    try:
        vid = int(data.get("video_id"))
    except (TypeError, ValueError):
        vid = next(iter(valid_ids))
    if vid not in valid_ids:
        vid = next(iter(valid_ids))
    alts = []
    for a in data.get("alternatives", []) or []:
        try:
            ai = int(a)
        except (TypeError, ValueError):
            continue
        if ai in valid_ids and ai != vid:
            alts.append(ai)
    try:
        conf = float(data.get("confidence", 0.6))
    except (TypeError, ValueError):
        conf = 0.6
    return {
        "video_id": vid,
        "reasoning": str(data.get("reasoning", "")).strip(),
        "confidence": max(0.0, min(conf, 1.0)),
        "alternatives": alts[:2],
    }


# ── Modo demo (sin API key) ──────────────────────────────────────────────────

_PAIN_KEYWORDS = {
    "no-show": ["no-show", "no aparec", "no asist", "asistencia", "plant", "falta a la"],
    "leads se enfrían": ["enfría", "enfrian", "frío", "frio", "tarda", "velocidad", "responder"],
    "falta de seguimiento": ["seguimiento", "follow", "no contacta", "no hace seguimiento"],
    "base de datos sin explotar": ["base de datos", "bbdd", "leads antiguos", "reactiv", "dormidos"],
    "comerciales saturados": ["saturad", "sdr", "equipo", "carga", "muchos leads"],
    "no cierran": ["no cierra", "cierre", "convertir", "conversion", "conversión"],
}


def _detect_pain(text: str) -> str:
    low = text.lower()
    best, score = "leads se enfrían", 0
    for pain, kws in _PAIN_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in low)
        if hits > score:
            best, score = pain, hits
    return best


def _mock_classify(title: str, description: str) -> dict:
    pain = _detect_pain(f"{title} {description}")
    return {
        "summary": f"[DEMO] Vídeo sobre «{title[:80]}». Ataca el dolor: {pain}.",
        "stage": "pre-call",
        "pain_category": pain,
        "use_case": f"[DEMO] Enviar a leads con el problema de: {pain}.",
        "tags": [
            {"name": pain, "type": "dolor", "confidence": 0.6},
            {"name": "pre-call", "type": "fase", "confidence": 0.55},
        ],
    }


def _mock_recommend(lead_context: str, candidates: list[dict]) -> dict:
    pain = _detect_pain(lead_context)

    def score(c: dict) -> int:
        blob = f"{c.get('title','')} {c.get('summary','')} {c.get('pain_category','')} {' '.join(c.get('tags', []))}".lower()
        return sum(1 for kw in _PAIN_KEYWORDS.get(pain, []) if kw in blob)

    ranked = sorted(candidates, key=score, reverse=True)
    best = ranked[0]
    alts = [c["id"] for c in ranked[1:3]]
    return {
        "video_id": best["id"],
        "reasoning": f"[DEMO] El lead refleja el dolor «{pain}» y este vídeo es el más cercano por título/etiquetas.",
        "confidence": 0.4,
        "alternatives": alts,
    }
