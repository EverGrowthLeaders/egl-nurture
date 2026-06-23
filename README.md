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
   | `SECRET_KEY` | cadena aleatoria (salt para hashear IPs) |
   | `ADMIN_TOKEN` | (opcional) protege los `POST /api/*` |
   | `DEFAULT_SETTER` | (opcional) nombre del setter por defecto en el mensaje |
   | `MESSAGE_TEMPLATE` | (opcional) plantilla del mensaje; placeholders `{setter} {link} {contact_name} {pain}` |

   > El `docker-compose.yml` construye `DATABASE_URL` solo a partir de `POSTGRES_USER/PASSWORD/DB` y levanta su **propio Postgres** con volumen persistente. No necesitas una base de datos externa.

3. **Asigna un dominio** al servicio `app` (puerto **8000**) desde la pestaña *Domains* de Dokploy. Traefik enruta el tráfico; puedes borrar la sección `ports` del compose si usas solo el dominio.
4. **Deploy.** Al arrancar, la app crea las tablas y siembra el vocabulario de etiquetas automáticamente.

> ⚠️ **Importante:** pon `BASE_URL` igual al dominio público real, porque es lo que se usa para construir los links `/r/<token>` que envías a los leads.

> 🔒 El dashboard web (`/`, `/recommend`, `/links`) **no** lleva login. Protégelo a nivel de Dokploy/Traefik (Basic Auth) o detrás de tu red. `ADMIN_TOKEN` solo protege la API JSON.

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

Base: `https://tu-dominio`. Los `POST` mutantes exigen cabecera `X-Admin-Token` **si** definiste `ADMIN_TOKEN`.

| Método | Ruta | Cuerpo / notas |
|---|---|---|
| `GET` | `/healthz` | estado y modo del LLM |
| `GET` | `/api/videos?status=active` | lista la biblioteca |
| `GET` | `/api/videos/{id}` | detalle de un vídeo |
| `POST` | `/api/videos` | `{"url":"https://youtu.be/..."}` → ingiere y clasifica |
| `POST` | `/api/videos/{id}/approve` | `{"approve_all_tags":true}` → activa el vídeo |
| `POST` | `/api/recommend` | `{"context":"el lead dijo..."}` → vídeo + razonamiento + alternativas |
| `POST` | `/api/links` | `{"video_id":2,"contact_id":"ghl_123","setter_name":"Laura","context":"..."}` → devuelve `url` trackeada, `redirect_url` y `message` final |
| `GET` | `/r/{token}` | redirección pública que registra el click |

Flujo típico por lead (p.ej. desde n8n / GHL):

```bash
# 1) DeepSeek elige el vídeo según el diagnóstico del lead
curl -X POST https://tu-dominio/api/recommend \
  -H 'content-type: application/json' \
  -d '{"context":"Agendan pero no aparecen a la llamada"}'
# → {"video": {"id": 2, ...}, ...}

# 2) Generas el link + mensaje para ese lead (contact_id de GHL + setter)
curl -X POST https://tu-dominio/api/links \
  -H 'content-type: application/json' \
  -d '{"video_id":2,"contact_id":"ghl_abc","setter_name":"Laura"}'
# → {"url":"https://tu-dominio/r/8e6RDPb",
#    "redirect_url":"https://www.youtube.com/watch?v=...&list=...",
#    "message":"Por lo que has hablado con \"Laura\" ... : https://tu-dominio/r/8e6RDPb"}
```

---

## Notas

- **Modelo DeepSeek:** por defecto `deepseek-ai/DeepSeek-V4-Flash` (rápido, MoE 284B/13B activos, contexto 1M). Verifica el slug exacto en la página del modelo en deepinfra.com y ponlo en `DEEPINFRA_MODEL`. La app habla con el endpoint OpenAI-compatible `…/v1/openai/chat/completions`.
- **Transcripción:** es opcional en v1. Si YouTube no la expone (o limita la IP del servidor), el vídeo se clasifica igualmente con título + descripción. La transcripción se guarda en `content_videos.transcript` cuando está disponible.
- **yt-dlp:** YouTube cambia su web a menudo. Si la ingesta empieza a fallar, actualiza la dependencia: en el contenedor reconstruye la imagen tras subir la versión de `yt-dlp` en `requirements.txt`.
- **"Sign in to confirm you're not a bot" (servidores):** YouTube bloquea las IPs de datacenter (como las de Dokploy). La app lo maneja así:
  1. **Sin configurar nada**, si yt-dlp es bloqueado usa un respaldo vía **oEmbed** (endpoint público) y la ingesta funciona igual con **título + miniatura + canal**; descripción/duración/transcripción quedan vacías y las completas a mano o las propone la IA desde el título.
  2. **Para metadata completa + transcripción**, dale cookies de una sesión de YouTube:
     - Exporta un `cookies.txt` (formato Netscape) desde tu navegador con sesión iniciada (extensión "Get cookies.txt", o `yt-dlp --cookies-from-browser`).
     - Móntalo en el contenedor (en `docker-compose.yml` hay un ejemplo de `volumes`) y pon `YTDLP_COOKIEFILE=/cookies.txt` en el Environment de Dokploy.
     - Opcional: `YTDLP_PLAYER_CLIENT=android,web,tv` para probar otros clientes.
- **URL tal cual:** al ingerir, se guarda la URL exactamente como la pegas (incluido `&list=...`). Para metadata/dedup se extrae el ID del vídeo, pero el redirect `/r/<token>` lleva al lead a esa URL completa (playlist). Puedes editarla en la ficha del vídeo.
- **Mensaje:** sigue `MESSAGE_TEMPLATE` (placeholders `{setter} {link} {contact_name} {pain}`). Si borras `{link}` de la plantilla, el enlace se añade igualmente al final para no enviar un mensaje sin link.
- **Clicks de bots/previews:** WhatsApp, Telegram, Slack, etc. precargan el link y generarían un "click" falso. Se registran como `is_bot=true` y **no** marcan al lead como caliente (`human_click_count`).
- **Migraciones:** v1 crea las tablas con `create_all` al arrancar. Para cambios de esquema en producción conviene añadir Alembic.

---

## Estructura del proyecto

```
app/
  main.py            # FastAPI + lifespan (init DB)
  config.py          # settings desde entorno
  db.py              # engine + sesión (Postgres/SQLite)
  models.py          # las 5 tablas
  seed.py            # vocabulario de etiquetas
  demo.py            # datos de demo (python -m app.demo)
  schemas.py         # esquemas API
  auth.py            # X-Admin-Token
  templating.py      # Jinja2 compartido
  services/
    youtube.py       # yt-dlp + youtube-transcript-api
    llm.py           # DeepInfra/DeepSeek + modo demo
    ingest.py        # orquesta la ingesta
    recommend.py     # prescripción de vídeo
    links.py         # tokens + tracking de clicks
  routers/
    api.py           # API JSON
    ui.py            # dashboard
    redirect.py      # /r/{token}
  templates/  static/
Dockerfile  docker-compose.yml  requirements.txt  .env.example
```
