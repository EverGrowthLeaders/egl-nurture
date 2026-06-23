# 📡 EGL Nurture Signal

Sistema para convertir tus vídeos de YouTube en una **biblioteca de activos comerciales** que prescribe el vídeo correcto a cada lead y mide la señal de interés:

1. **Ingiere** un vídeo desde su URL → extrae metadata (yt-dlp) + transcripción. La URL se guarda **tal cual** (puede llevar `&list=...` de playlist) y es a donde redirige el link.
2. **Clasifica** el vídeo con **DeepSeek vía DeepInfra** (dolor, fase del embudo, caso de uso, etiquetas) — la IA propone, tú apruebas.
3. **Recomienda** el mejor vídeo para un lead concreto a partir de su diagnóstico ("prescripción de contenido").
4. **Genera el mensaje** (con tu plantilla fija) + un **link único trackeado** por (vídeo + lead) y registra los clicks (distinguiendo humanos de previews/bots).

> La frase clave: **primero construyes la biblioteca; luego el sistema prescribe el activo correcto a cada lead.**

---

## Arquitectura

```
URL de YouTube
   │  yt-dlp (metadata)  +  youtube-transcript-api (transcripción)
   ▼
DeepSeek (DeepInfra)  →  resumen + dolor + fase + etiquetas   [IA propone]
   ▼
Revisión humana en el dashboard  →  ACTIVO                    [tú apruebas]
   ▼
Lead concreto  →  DeepSeek elige vídeo + redacta mensaje
   ▼
Link trackeado  /r/<token>?c=<contact_id>  →  página Open Graph (miniatura)
                                            →  registra click (humano vs bot)
                                            →  redirige a la URL/playlist de YouTube
```

Stack: **FastAPI + SQLAlchemy + Jinja2**, **Postgres** (en producción), **DeepInfra** (OpenAI-compatible). Desplegable en **Dokploy** con `docker-compose.yml`.

### Las 5 tablas

| Tabla | Para qué |
|---|---|
| `content_videos` | La biblioteca: metadata, transcripción, clasificación comercial y estado. |
| `content_tags` | Vocabulario comercial (`dolor`, `fase`, `objecion`). |
| `video_tags` | Relación vídeo ↔ etiqueta, con `confidence`, `source` y `approved`. |
| `tracked_content_links` | Un link único por lead, con su mensaje y contadores de clicks. |
| `content_click_events` | Histórico de cada click (UA, IP hasheada, `is_bot`). |

---

## Despliegue en Dokploy (recomendado)

1. **Crea una aplicación de tipo *Docker Compose*** en Dokploy apuntando a este repo (o sube los ficheros).
2. En **Environment**, pega las variables (ver `.env.example`). Las imprescindibles:

   | Variable | Valor |
   |---|---|
   | `POSTGRES_PASSWORD` | una contraseña fuerte |
   | `DEEPINFRA_API_KEY` | tu API key de DeepInfra |
   | `DEEPINFRA_MODEL` | slug exacto del modelo, por defecto `deepseek-ai/DeepSeek-V4-Flash` |
   | `BASE_URL` | el dominio público que asignes, p.ej. `https://video.tudominio.com` |
   | `SECRET_KEY` | cadena aleatoria (firma la sesión de login y hashea IPs) |
   | `BOOTSTRAP_ADMIN_EMAIL` | email de la primera cuenta (se crea al arrancar) |
   | `BOOTSTRAP_ADMIN_PASSWORD` | contraseña de esa cuenta |
   | `BOOTSTRAP_TENANT_NAME` | (opcional) nombre del workspace, p.ej. `EGL` |

   > El `docker-compose.yml` construye `DATABASE_URL` solo a partir de `POSTGRES_USER/PASSWORD/DB` y levanta su **propio Postgres** con volumen persistente. No necesitas una base de datos externa.

3. **Asigna un dominio** al servicio `app` (puerto **8000**) desde la pestaña *Domains* de Dokploy. Traefik enruta el tráfico; puedes borrar la sección `ports` del compose si usas solo el dominio.
4. **Deploy.** Al arrancar, la app migra/crea las tablas, crea tu cuenta (si pusiste `BOOTSTRAP_*`) y reasigna los datos previos a tu workspace.

> ⚠️ **Importante:** pon `BASE_URL` igual al dominio público real, porque es lo que se usa para construir los links `/r/<token>` que envías a los leads.

### Cuentas (multi-tenant, invite-only)

Cada **cuenta = un workspace (tenant)** con sus vídeos, links y settings aislados. No hay registro abierto: las cuentas se crean con `BOOTSTRAP_*` (la primera) o por CLI:

```bash
# dentro del contenedor app (Dokploy → Terminal del servicio)
python -m app.admin create-tenant --name "Cliente X" --email cliente@x.com --password secreto
python -m app.admin list
python -m app.admin set-password --email cliente@x.com --password nueva
```

Entras por `/login`. En **Settings** cada usuario configura su setter por defecto, su plantilla de mensaje, su conexión a GHL y su API key.

### Integración GoHighLevel

En **Settings** pegas tu **Private Integration Token** (API v2) y tu **Location ID**; el sistema lista tus *custom fields* y eliges en cuál escribir. Cuando un lead **ve el vídeo** (click humano), el software escribe ese campo en el contacto (`contact_id`) formateando el valor según el tipo de campo: `DATE` → fecha, `CHECKBOX`/opciones → "Sí", numérico → 1, texto → "Visto {fecha}" (o el valor que fijes).

---

## Desarrollo local

Sin Docker, usando SQLite (cero configuración) y **modo demo** del LLM (sin API key, sin gastar tokens):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL="sqlite:///./data/library.db"   # opcional; es el valor por defecto
python -m app.demo                                   # inserta 4 vídeos de ejemplo (activos)

uvicorn app.main:app --reload --port 8000
# abre http://localhost:8000
```

- **Modo demo:** si `DEEPINFRA_API_KEY` está vacío, la clasificación y la recomendación usan un mock determinista por palabras clave, para que veas el flujo completo. `GET /healthz` indica `"llm":"demo"` o `"live"`.
- Para probar en vivo en local, exporta `DEEPINFRA_API_KEY` y `DEEPINFRA_MODEL`.

Con Docker en local: `docker compose up --build` (levanta Postgres + app en el puerto 8000).

---

## Flujo en el dashboard

1. **Biblioteca** (`/`): pega la URL de YouTube (la de la **playlist** si quieres que consuma más) → *Ingerir*. El vídeo queda *en revisión* con la clasificación propuesta.
2. **Ficha del vídeo**: corrige resumen/dolor/fase, edita la URL de redirect si hace falta, marca las etiquetas que apruebas y pulsa **Activar**. Solo los vídeos **activos** entran en el recomendador.
3. **Recomendar** (`/recommend`): mete el **contact_id de GHL** + el **diagnóstico** del lead → DeepSeek elige el vídeo. Pones el **setter** (con quién habló) y se genera el mensaje con tu plantilla + el link.
4. **Links** (`/links`): ve todos los links, sus clicks y qué leads están 🔥 *calientes* (han hecho click humano). En la ficha del link copias el mensaje listo para pegar en GHL/Chatwoot.

### El mensaje

Sigue una **plantilla fija** (configurable en `MESSAGE_TEMPLATE`), por defecto:

> Por lo que has hablado con "**{setter}**" y lo que has rellenado te paso este vídeo, que es muy importante que veas antes de la llamada, te va a ayudar a entender todo mejor: **{link}**

- `{setter}` → el nombre que metes por lead (o `DEFAULT_SETTER`).
- `{link}` → el **link trackeado** `/r/<token>?c=<contact_id>`. Ese link devuelve una página con etiquetas Open Graph (la miniatura del vídeo), así que **mantiene el preview en WhatsApp/Telegram a la vez que registra el click**, y luego redirige a tu URL de playlist.
- **Contact ID en la URL:** el link lleva `?c=<contact_id>` (el de GHL). Al generarlo por lead se rellena solo; también puedes usar un link reutilizable y pasar el contacto con un merge field de GHL (`?c={{contact.id}}`) — el redirect lo lee y lo asocia al click.

---

## API JSON (para n8n / GHL / Chatwoot)

Base: `https://tu-dominio`. **Todas** las llamadas a `/api/*` exigen la cabecera `X-Api-Key` con la API key de tu workspace (la ves en Settings). Cada key resuelve su tenant y aísla los datos.

| Método | Ruta | Cuerpo / notas |
|---|---|---|
| `GET` | `/healthz` | estado y modo del LLM |
| `GET` | `/api/videos?status=active` | lista la biblioteca |
| `GET` | `/api/videos/{id}` | detalle de un vídeo |
| `POST` | `/api/videos` | `{"url":"https://youtu.be/..."}` → ingiere y clasifica |
| `POST` | `/api/videos/{id}/approve` | `{"approve_all_tags":true}` → activa el vídeo |
| `POST` | `/api/recommend` | `{"context":"el lead dijo..."}` → vídeo + razonamiento + alternativas |
| `POST` | `/api/links` | `{"video_id":2,"contact_id":"ghl_123","setter_name":"Laura","context":"..."}` → devuelve `url` trackeada, `redirect_url` y `message` final |
| `GET` | `/api/links?contact_id=ghl_123&video_id=2` | ¿abrió el contacto el vídeo? Devuelve los links con `opened` (bool), clicks y timestamps |
| `GET` | `/api/links/{token}` | estado de un link concreto (`opened`, clicks, fechas) |
| `GET` | `/r/{token}` | redirección pública: preview tipo YouTube + registra el click |
| `GET` | `/thumb/{youtube_id}.jpg` | miniatura compuesta (play + marca de agua YouTube) usada como `og:image` |

Flujo típico por lead (p.ej. desde n8n / GHL):

```bash
# 1) DeepSeek elige el vídeo según el diagnóstico del lead
curl -X POST https://tu-dominio/api/recommend \
  -H 'X-Api-Key: TU_API_KEY' -H 'content-type: application/json' \
  -d '{"context":"Agendan pero no aparecen a la llamada"}'
# → {"video": {"id": 2, ...}, ...}

# 2) Generas el link + mensaje para ese lead (contact_id de GHL + setter)
curl -X POST https://tu-dominio/api/links \
  -H 'X-Api-Key: TU_API_KEY' -H 'content-type: application/json' \
  -d '{"video_id":2,"contact_id":"ghl_abc","setter_name":"Laura"}'
# → {"url":"https://tu-dominio/r/8e6RDPb",
#    "redirect_url":"https://www.youtube.com/watch?v=...&list=...",
#    "message":"Por lo que has hablado con \"Laura\" ... : https://tu-dominio/r/8e6RDPb"}

# 3) (más tarde) ¿abrió el contacto el vídeo? → workflow en GHL
#    (al abrirlo, además, se escribe el campo elegido en el contacto de GHL)
curl -H 'X-Api-Key: TU_API_KEY' "https://tu-dominio/api/links?contact_id=ghl_abc&video_id=2"
# → [{"opened": true, "first_clicked_at": "...", "human_click_count": 1, ...}]
```

---

## Notas

- **Modelo DeepSeek:** por defecto `deepseek-ai/DeepSeek-V4-Flash` (rápido, MoE 284B/13B activos, contexto 1M). Verifica el slug exacto en la página del modelo en deepinfra.com y ponlo en `DEEPINFRA_MODEL`. La app habla con el endpoint OpenAI-compatible `…/v1/openai/chat/completions`.
- **Preview tipo YouTube:** el link `/r/<token>` expone como `og:image` una miniatura compuesta (`/thumb/<id>.jpg`) con el botón de play y la marca de agua "YouTube" ya integrados, para que en WhatsApp/Telegram se vea como un vídeo de YouTube real (las apps solo añaden ese aspecto a enlaces de `youtube.com`, no a dominios propios). Requiere que `BASE_URL` sea tu dominio público https. Las apps cachean el preview de forma agresiva: cada token nuevo genera una URL nueva, así que se ve fresco.
- **Transcripción:** es opcional en v1. Si YouTube no la expone (o limita la IP del servidor), el vídeo se clasifica igualmente con título + descripción. La transcripción se guarda en `content_videos.transcript` cuando está disponible.
- **yt-dlp:** YouTube cambia su web a menudo. Si la ingesta empieza a fallar, actualiza la dependencia: en el contenedor reconstruye la imagen tras subir la versión de `yt-dlp` en `requirements.txt`.
- **"Sign in to confirm you're not a bot" (servidores):** YouTube bloquea las IPs de datacenter (como las de Dokploy). La app lo maneja así:
  1. **Sin configurar nada**, si yt-dlp es bloqueado usa un respaldo vía **oEmbed** (endpoint público) y la ingesta funciona igual con **título + miniatura + canal**; descripción/duración/transcripción quedan vacías y las completas a mano o las propone la IA desde el título.
  2. **Para metadata completa + transcripción**, dale cookies de una sesión de YouTube:
     - Exporta un `cookies.txt` (formato Netscape) desde tu navegador con sesión iniciada (extensión "Get cookies.txt", o `yt-dlp --cookies-from-browser`).
     - Móntalo en el contenedor (en `docker-compose.yml` hay un ejemplo de `volumes`) y pon `YTDLP_COOKIEFILE=/cookies.txt` en el Environment de Dokploy.
     - Opcional: `YTDLP_PLAYER_CLIENT=android,web,tv` para probar otros clientes.
- **URL tal cual:** al ingerir, se guarda la URL exactamente como la pegas (incluido `&list=...`). Para metadata/dedup se extrae el ID del vídeo, pero el redirect `/r/<token>` lleva al lead a esa URL completa (playlist). Puedes editarla en la ficha del vídeo.
- **Mensaje:** sigue la plantilla del tenant (Settings; placeholders `{setter} {link} {contact_name} {pain}`). Si borras `{link}`, el enlace se añade igualmente al final para no enviar un mensaje sin link.
- **Clicks de bots/previews:** WhatsApp, Telegram, Slack, etc. precargan el link y generarían un "click" falso. Se registran como `is_bot=true` y **no** marcan al lead como caliente (`human_click_count`) ni disparan la escritura en GHL.
- **Migraciones:** al arrancar se crean las tablas nuevas y se añade `tenant_id` a las existentes (migración ligera, idempotente), reasignando los datos previos a tu workspace. Para esquemas más complejos conviene añadir Alembic.

---

## Estructura del proyecto

```
app/
  main.py            # FastAPI + sesión + lifespan (init/migración DB)
  config.py          # settings globales (DB, DeepInfra, BASE_URL, bootstrap)
  db.py              # engine + sesión + migración ligera (Postgres/SQLite)
  models.py          # Tenant, User + las 5 tablas (scoped por tenant)
  bootstrap.py       # crea tenant/usuario inicial + backfill de datos previos
  security.py        # hashing de contraseñas (PBKDF2) + api keys
  auth.py            # sesión de login + X-Api-Key por tenant
  admin.py           # CLI: crear cuentas (python -m app.admin)
  seed.py            # vocabulario de etiquetas (por tenant)
  demo.py            # datos de demo (python -m app.demo)
  schemas.py         # esquemas API
  templating.py      # Jinja2 compartido
  services/
    youtube.py       # yt-dlp (+ oEmbed) + youtube-transcript-api
    llm.py           # DeepInfra/DeepSeek + modo demo
    ingest.py        # orquesta la ingesta
    recommend.py     # prescripción de vídeo
    links.py         # tokens + tracking de clicks
    thumbnail.py     # miniatura estilo YouTube (Pillow)
    ghl.py           # GoHighLevel v2 (campos + escritura type-aware)
  routers/
    account.py       # login / logout
    settings.py      # Settings del tenant (setter, plantilla, GHL)
    api.py           # API JSON (X-Api-Key)
    ui.py            # dashboard
    redirect.py      # /r/{token} (preview + tracking + GHL)
    preview.py       # /thumb/{id}.jpg
  templates/  static/
Dockerfile  docker-compose.yml  requirements.txt  .env.example
```
