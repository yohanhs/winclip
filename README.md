# WinClip

WinClip (nombre de código; la marca visible se configura con `APP_NAME`) es una aplicación **local** de
clipping: a partir de un vídeo largo (URL o archivo) genera cortes verticales 9:16 con subtítulos
palabra a palabra, siguiendo las reglas de una campaña, los revisa en una web y los publica en cuentas
de YouTube, TikTok e Instagram ya configuradas.

> Estado: **pipeline local completo, API/cola SSE, reglas de campaña (`/campaigns`), gestión de cuentas
> sociales (`/accounts`), publicación y programación multi-cuenta (`/publications`), interfaz web de
> proyectos y revisión de clips 9:16 con controles avanzados de edición por clip** (corrección inline de
> palabras de subtítulos sin alterar `transcript.json`, override de preset y modo de reencuadre, y
> ajuste manual de `crop_x`/`crop_y`/`zoom` en modo `center`).

## Requisitos

- macOS en Apple Silicon (objetivo: M1, 16 GB).
- [Node.js](https://nodejs.org) 24+ (hay `.nvmrc` con `24`) y [pnpm](https://pnpm.io) 10+.
- [uv](https://docs.astral.sh/uv/) (gestiona Python 3.12 automáticamente).
- `ffmpeg-full` de Homebrew **con libass** (keg-only, no está en el `PATH`):

  ```bash
  brew install ffmpeg-full
  # FFMPEG_BIN=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
  ```

- `yt-dlp` (`brew install yt-dlp`).
- Opcionales: Ollama con modelos locales y Playwright/Chromium para publicar sin API.

## Puesta en marcha

```bash
pnpm install                 # dependencias JS del monorepo
cp .env.example .env         # configuración local (ignorada por git)
pnpm dev                     # API :8000 + worker + web :3000
```

`pnpm dev` lanza tres procesos: `api` (uvicorn con recarga), `worker` (cola de trabajos) y `web`.
La API y el worker aplican las migraciones de Alembic al arrancar y crean `workspace` por defecto.

- Web: <http://localhost:3000> · Estado del sistema: <http://localhost:3000/settings/status>
- API: <http://localhost:8000/api/health> · OpenAPI: <http://localhost:8000/openapi.json>
- Worker solo: `uv run --project apps/api winclip worker` · Migraciones: `winclip db upgrade`

## Diagnóstico

```bash
uv run --project apps/api winclip doctor
```

Comprueba ffmpeg-full (filtros `ass` y `subtitles`), ffprobe, yt-dlp, el modelo Whisper en la caché de
Hugging Face, Ollama, Chromium de Playwright, el volumen externo y que `STORAGE_DIR` sea escribible.
Los servicios opcionales solo generan `warn`; un `error` hace que el comando termine con código 1.
Las claves de API se muestran únicamente como `presente`/`ausente`, nunca su valor.

## Pipeline: ingesta y transcripción (CLI)

Los changes 1–3 se validan solo por CLI antes de construir la API y la web.

```bash
# URL remota (mejor MP4 <= 1080p) o archivo local (.mp4, .mov, .mkv, .webm)
uv run --project apps/api winclip ingest "https://www.youtube.com/watch?v=..."
uv run --project apps/api winclip ingest /ruta/video.mov --project-id mi-proyecto

# transcripción local con timestamps por palabra
uv run --project apps/api winclip transcribe mi-proyecto --language es
uv run --project apps/api winclip transcribe mi-proyecto --model tiny --force
```

- `ingest [--project-id <id>] [--force]`: descarga o copia el video, inspecciona con `FFPROBE_BIN`
  (`source/meta.json`) y extrae `audio/audio16k.wav` (WAV PCM mono 16 kHz) con `FFMPEG_BIN`.
  `--project-id` acepta `[a-z0-9_-]` (2–64 caracteres); si se omite se genera un ULID en minúsculas.
  Sin `--force` un proyecto ya ingestado se rechaza para no sobrescribirlo.
- `transcribe [--language es|en|auto] [--model <repo|tiny>] [--force]`: transcribe en local con
  `mlx-whisper` (`word_timestamps=True`). Por defecto usa `WHISPER_MODEL` y autodetecta el idioma.
  Reutiliza `transcript/transcript.json` si ya es válido salvo con `--force`.

Cada proyecto queda aislado bajo `STORAGE_DIR/projects/<project_id>/`:

```
source/original.<ext>       video descargado o copiado (el original no se modifica)
source/meta.json            metadatos de ffprobe y de yt-dlp
audio/audio16k.wav          audio normalizado mono 16 kHz
transcript/transcript.json  contrato `docs/architecture.md §6.1`
```

Las pruebas lentas (`pytest -m slow`) ejecutan `mlx-whisper` real con el modelo `tiny` y solo corren en
macOS arm64 con el modelo en caché de Hugging Face.

## Selección de clips con LLM (CLI)

`winclip select` lee `transcript/transcript.json`, segmenta la transcripción en frases y pide a un
router de proveedores **gratuitos** los mejores clips. Los modelos por defecto son configurables en
`.env` (véase `.env.example`):

| Variable | Modelo por defecto |
|---|---|
| `GEMINI_MODEL` | `gemini-3.8-flash` |
| `NVIDIA_MODEL` | `nvidia/nemotron-3.5-lightning-30b-a3b` |
| `OPENROUTER_MODEL` | `nvidia/nemotron-3.5-lightning:free` |
| `GROQ_MODEL` | `qwen/qwen3.8-27b` |
| `OLLAMA_MODEL` | `qwen3.5:4b` |

El orden lo define `LLM_PROVIDER_ORDER` (`gemini,nvidia,openrouter,groq,ollama`). Los proveedores sin
clave (o sin servicio, como Ollama) se omiten; ante 429/5xx/timeouts hay backoff acotado y fallback, y
una respuesta JSON inválida se autocorrige hasta dos veces antes de pasar al siguiente proveedor. Las
respuestas válidas se cachean en `STORAGE_DIR/cache/llm/<sha256>.json` y la caché nunca contiene claves.

```bash
# comprobar qué proveedor responde (sale con código 1 si ninguno lo hace)
uv run --project apps/api winclip llm test

# seleccionar 5 clips y escribir selection/candidates.json
uv run --project apps/api winclip select mi-proyecto --count 5

# todos los clips que superen LLM_SCORE_THRESHOLD (60), aplicando reglas de campaña
uv run --project apps/api winclip select mi-proyecto --count max --rules rules.json

# ignorar la caché local de respuestas LLM
uv run --project apps/api winclip select mi-proyecto --count 5 --no-cache
```

`rules.json` sigue el esquema de `docs/architecture.md §6.4` y todos sus campos son opcionales:

```json
{
  "name": "mi-campana",
  "language": "es",
  "min_duration": 20,
  "max_duration": 60,
  "max_clips": 5,
  "banned_words": ["estafa"],
  "required_keywords": ["dinero"],
  "tone": "directo",
  "hashtags": ["#shorts", "#finanzas"]
}
```

Post-procesado determinista: cortes ajustados a palabras reales de la transcripción, duración dentro
del rango, descarte de candidatos con `banned_words`, aviso estructurado (`rule_violations`) si faltan
`required_keywords`, ausencia de solapes y orden por `score` descendente. `--count max` exige además
`score >= LLM_SCORE_THRESHOLD` y cero infracciones. El resultado queda en
`STORAGE_DIR/projects/<project_id>/selection/candidates.json` (contrato §6.2).

## Render de clips verticales (CLI)

`winclip render` toma los candidatos de `selection/candidates.json` y produce en
`STORAGE_DIR/projects/<project_id>/clips/<clip_id>/` exactamente `clip.mp4` (1080x1920),
`thumb.jpg`, `subs.ass` y `render.json` (contrato §6.3). El vídeo se codifica con
`h264_videotoolbox` en Apple Silicon y cae automáticamente a `libx264` cuando el binario no
lo soporta (Linux/CI); el audio va a AAC 192 kbps con `loudnorm` a `-14 LUFS`.

```bash
# un candidato concreto
uv run --project apps/api winclip render mi-proyecto --clip 01jcand --preset bold-yellow

# todos los candidatos con otro preset y el motor PIL
uv run --project apps/api winclip render mi-proyecto --all --preset hormozi --engine pil

# reencuadre manual con zoom y sin hook
uv run --project apps/api winclip render mi-proyecto --clip 01jcand --reframe center \
  --crop-x-pct 30 --zoom-pct 125 --no-hook-overlay
```

| Opción | Valores | Descripción |
|---|---|---|
| `--clip <id>` / `--all` | uno de los dos | candidato a renderizar o todos |
| `--preset` | `bold-yellow`, `hormozi`, `clean-white`, `mrbeast` | estilo de subtítulos |
| `--reframe` | `face`, `center`, `blur` | seguimiento facial, recorte manual o fondo desenfocado |
| `--engine` | `ass` (libass, por defecto), `pil` | motor de subtítulos |
| `--font` | nombre de fuente | p. ej. `GothamBlack` desde `USER_FONTS_DIR` |
| `--crop-x-pct`, `--crop-y-pct`, `--zoom-pct` | `0-100`, `100-300` | ajustes del modo `center` |
| `--hook-overlay` / `--no-hook-overlay`, `--hook-seconds` | `0.5-10` | tarjeta del hook al inicio |
| `--watermark <png>` | ruta | marca de agua en la esquina superior derecha |
| `--force` | — | vuelve a renderizar aunque la huella coincida |

Presets en `assets/subtitle-presets/*.json` (tipografía, colores, contorno, zona segura y
agrupación). Las fuentes OFL viven en `assets/fonts/` (incluida `Noto Color Emoji`); si se pide
una fuente que no existe, se avisa y se usa la fuente OFL de respaldo del preset.

El reencuadre `face` descarga una sola vez `face_detection_yunet_2023mar.onnx` en
`STORAGE_DIR/models/` con verificación SHA-256; sin red, usa `--reframe center` o `blur`. Los
clips son idempotentes: la huella de parámetros se guarda en `.render.sha256` y una segunda
ejecución reutiliza el clip salvo `--force` o cambio de preset. Un fallo a mitad de render no deja
artefactos porque todo se escribe en un directorio temporal y se publica de forma atómica.

## API, trabajos y eventos en tiempo real

La API REST (`/api`) persiste proyectos, clips y trabajos en SQLite y expone la cola asíncrona que
procesa el worker. Contrato completo en [`docs/api.md`](docs/api.md).

```bash
# crear un proyecto desde una URL (JSON) o desde un archivo (multipart streaming)
curl -s -X POST http://127.0.0.1:8000/api/projects \
  -H 'content-type: application/json' \
  -d '{"source_url":"https://www.youtube.com/watch?v=...","requested_clips":5,"language":"es"}'

# seguir el progreso en tiempo real
curl -N 'http://127.0.0.1:8000/api/events?project_id=<id>'
```

- Proyectos: `POST/GET/DELETE /api/projects` y `GET /api/projects/{id}/clips`.
- Campañas: `GET/POST/PATCH/DELETE /api/campaigns`, `POST /api/campaigns/{id}/duplicate`,
  `GET /api/campaigns/templates` (plantillas ES/EN en `assets/campaign-templates/`),
  `POST /api/campaigns/parse` (convierte un brief en texto libre en reglas propuestas con
  `inferred_fields` sin persistir) y `POST /api/campaigns/watermarks` (subida segura PNG/WebP ≤ 5 MB).
- Clips: `PATCH/DELETE /api/clips/{id}`, `POST /api/clips/{id}/rerender` y entrega de MP4/JPEG con
  `Range` y `206` en `/file` y `/thumb`.
- Trabajos: `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel` (`409` si ya terminó).
- Presets: `GET /api/presets` lee `assets/subtitle-presets/*.json`.
- SSE: `job.progress`, `job.done`, `job.failed`, `clip.ready` y `heartbeat`, con `Last-Event-ID`.

```bash
# listar plantillas de ejemplo ES/EN
curl -s http://127.0.0.1:8000/api/campaigns/templates

# analizar un brief en texto libre sin guardarlo (devuelve rules + inferred_fields)
curl -s -X POST http://127.0.0.1:8000/api/campaigns/parse \
  -H 'content-type: application/json' \
  -d '{"source_text":"Clips en español de 20 a 55s con #finanzas y sin decir garantizado."}'
```

La cola vive en la tabla `job`: un trabajo pesado a la vez (GPU/MLX/ffmpeg), concurrencia ligera
configurable, jobs diferidos con `run_at`, reintentos con backoff, cancelación cooperativa y
recuperación de huérfanos al reiniciar. Los jobs `publish` se ejecutan fuera del semáforo GPU.

## Interfaz web y cliente API tipado

La web (`apps/web`) consume el cliente TypeScript generado desde el esquema OpenAPI de FastAPI en
`packages/api-client` (`@winclip/api-client`):

```bash
# regenerar schema.d.ts y snapshot OpenAPI desde apps/api (sin levantar el servidor)
pnpm gen:api
```

Rutas principales:

- `/campaigns`: gestión de campañas con listado, plantillas de ejemplo ES/EN, duplicación,
  eliminación con confirmación, editor estructurado completo (incluyendo subida PNG/WebP de
  marca de agua), pestaña `"Pegar brief (IA)"` con badges violeta `IA` en `inferred_fields` y
  vista previa JSON sincronizada.
- `/projects`: listado de proyectos con métricas reales, filtros por estado/idioma, vista grid/lista,
  progreso en vivo por SSE y eliminación con confirmación.
- `/projects/new`: creación por URL (JSON) o archivo local (multipart con progreso real y cancelación),
  selector de campaña activa (heredando `requested_clips`, idioma y preset), cantidad de clips o
  modo `"Máximo posible"` (`"max"`), idioma (`auto`/`es`/`en`), reencuadre (`face`/`center`/`blur`/`passthrough`)
  y previsualización 9:16 en vivo del preset de subtítulos.
- `/projects/[id]`: stepper en vivo de las 4 etapas (`Descarga → Transcripción → Selección → Render`)
  con cancelación, filtro `"Alertas"`, grid responsive de cards 9:16 con `hover-play`, alertas de
  `rule_violations`, reproductor, edición de metadatos, recorte con mini timeline y re-renderizado,
  descarga MP4, eliminación, publicación individual y multiselección con `"Publicar en redes →"`.
- `/accounts`: gestión multi-cuenta para YouTube, TikTok e Instagram con tarjetas agrupadas,
  badges de método (`API Oficial` / `Playwright`) y estado (`Conectada` / `Expirada` / `Error`),
  cuenta por defecto por plataforma, renombrado de alias, prueba de conexión en vivo, reconexión,
  eliminación con confirmación y diálogo `"+ Conectar cuenta"` (OAuth oficial, navegador persistente
  e importación de tokens locales en modo solo lectura).
- `/publications`: historial multi-cuenta filtrable por estado (`Programadas`, `Publicando`,
  `Publicadas`, `Con error`, `Canceladas`), plataforma, cuenta y proyecto, con progreso en vivo vía
  SSE, enlace externo, visor modal `"Ver captura"`, botón `"Reintentar"` en fallidas y `"Cancelar"`
  en programadas.
- `/settings/status`: comprobaciones reales de `GET /api/health`.

## Publicación y programación multi-cuenta

Desde `/projects/[id]` puedes publicar uno o varios clips renderizados en múltiples cuentas a la vez
(cada par `clip × cuenta` genera un registro en `publication` y un job `publish` independiente con
idempotencia por `external_id` y límites diarios por cuenta):

- **YouTube Shorts (YouTube Data API v3):** sube con `MediaFileUpload` reanudable, valida título
  `<= 100` caracteres, añade descripción/tags/categoría/idioma/privacidad, soporta programación nativa
  en servidor (`privacyStatus="private"` + `publishAt`), miniatura personalizada y comentario inicial
  como pasos secundarios no fatales.
  - **Cuota diaria:** cada `videos.insert` consume ~1 600 unidades de la cuota estándar de **10 000
    unidades/día** (~6 subidas/día por proyecto Google). WinClip muestra el consumo diario estimado en
    `/api/publications/quota` y en el diálogo `"Publicar"`; ante `quotaExceeded` detiene el job sin
    reintentos ciegos.
- **TikTok (Content Posting API v2):** usa **Direct Post** (`video/init`) cuando la cuenta tiene el
  scope auditado `video.publish`; si solo dispone de `video.upload`, degrada automáticamente a
  **Borrador Inbox** (`inbox/video/init`, `delivery_mode="inbox"`) mostrando un aviso claro para
  completar la publicación desde la app móvil de TikTok.
- **Instagram Reels (Instagram Graph API):** usa subida reanudable binaria directa desde tu disco
  local hacia `rupload.facebook.com` (`upload_type=resumable`), sin exponer WinClip a internet ni
  depender de buckets en la nube; espera a que el contenedor alcance `FINISHED` antes de llamar a
  `media_publish`.
- **Programación diferida:** YouTube programa directamente en los servidores de Google. Para TikTok e
  Instagram, WinClip guarda el job con `run_at = scheduled_at` y lo dispara desde el worker local
  (requiere que WinClip y el worker estén activos a la hora programada; si el retraso supera la
  ventana configurada `PUBLISH_MISSED_SCHEDULE_WINDOW_SECONDS`, falla de forma segura para evitar
  publicaciones tardías inesperadas).
- **Respaldo Playwright (TikTok e Instagram) — Advertencia de ToS:** los Términos de Servicio de
  TikTok e Instagram restringen la automatización web; prioriza siempre las APIs oficiales. El
  respaldo Playwright usa navegador visible, pausas humanas, perfiles aislados, límite diario
  conservador (5/día) y capturas por paso bajo `STORAGE_DIR/publications/<id>/steps/`. Ante cualquier
  CAPTCHA, verificación humana, 2FA o sesión expirada, WinClip **se detiene inmediatamente** sin
  intentar resolver ni evadir el reto y guarda la captura diagnóstica para revisión manual.

## Cuentas sociales (OAuth, navegador e importación local)

WinClip almacena las credenciales OAuth cifradas con Fernet en `STORAGE_DIR/accounts/<id>/credentials.enc`
(permisos `0600`) usando una clave maestra guardada automáticamente en el Keychain de macOS vía `keyring`
(o sobrescribible mediante `WINCLIP_SECRET_KEY` en `.env` para entornos headless/CI). Los perfiles de
Playwright se aíslan en `STORAGE_DIR/accounts/<id>/profile/` (`0700`).

### Configuración OAuth (`.env`, fuera del repo)

- **YouTube Data API v3:** descarga el `client_secret_*.json` de una app OAuth en Google Cloud Console,
  guárdalo fuera del repo y define `GOOGLE_CLIENT_SECRET_FILE=/ruta/client_secret.json`. Añade como
  Redirect URI `http://localhost:8000/api/accounts/oauth/youtube/callback`.
  > Nota: en Google Cloud Console las apps en modo *Testing* caducan los refresh tokens cada 7 días;
  > cuando expiren, WinClip muestra el estado `Expirada` y permite reconectar en un clic.
- **TikTok Content Posting API:** define `TIKTOK_CLIENT_KEY` y `TIKTOK_CLIENT_SECRET` con Redirect URI
  `http://localhost:8000/api/accounts/oauth/tiktok/callback`. Si tu app solo tiene `video.upload` (sin
  `video.publish`), la cuenta se conecta en modo **Solo inbox** (borrador).
- **Instagram Graph (Meta):** define `META_APP_ID` y `META_APP_SECRET` con Redirect URI
  `http://localhost:8000/api/accounts/oauth/instagram/callback`. Requiere cuentas Business o Creator
  vinculadas a una página de Facebook; si hay varias, WinClip muestra un selector tras autorizar.
- **Navegador persistente (Playwright):** disponible para TikTok e Instagram sin claves de API. Abre
  Chromium visible para login manual y 2FA y persiste el perfil aislado por cuenta.

### CLI e importación de tokens locales

```bash
# listar cuentas conectadas
uv run --project apps/api winclip accounts list

# comprobar salud y refrescar tokens (todas o una cuenta concreta)
uv run --project apps/api winclip accounts check [account_id]

# importar un archivo JSON o una carpeta de tokens existentes en modo solo lectura
uv run --project apps/api winclip accounts import /ruta/a/tokens/ --alias "Canal Principal"
```

## Estructura

```
apps/api/            FastAPI + CLI + worker (Python 3.12, uv)
apps/api/alembic/    migraciones versionadas de SQLite (render_as_batch)
apps/web/            Next.js 16 (App Router, Tailwind v4, shadcn/ui)
packages/api-client/ cliente TypeScript generado desde OpenAPI (`pnpm gen:api`)
assets/fonts/        fuentes OFL con sus licencias
docs/architecture.md arquitectura y contratos entre changes
openspec/            especificaciones y changes (OpenSpec)
```

## Tests y lint

```bash
# Regenerar cliente API y comprobar tipos
pnpm gen:api
pnpm --filter @winclip/api-client typecheck

# API (Python)
uv run --project apps/api pytest
uv run --project apps/api ruff check . && uv run --project apps/api ruff format --check .

# Web (ESLint, TypeScript, Vitest, build y Playwright E2E)
pnpm lint
pnpm --filter web typecheck && pnpm --filter web build
pnpm --filter web test
pnpm --filter web test:e2e
```

## Seguridad

El repositorio es público: `.env`, `client_secret*.json`, tokens, cookies, perfiles de navegador,
`storage/` y la media quedan fuera de git, y [gitleaks](https://github.com/gitleaks/gitleaks) los
escanea en pre-commit y en CI. Nunca se imprimen secretos en logs ni en el diagnóstico.

## Licencia

[AGPL-3.0](LICENSE). Las fuentes incluidas en `assets/fonts` tienen licencia SIL Open Font License y
cada familia conserva su `OFL.txt`. Las fuentes comerciales no se distribuyen: se cargan en local desde
`USER_FONTS_DIR`.
