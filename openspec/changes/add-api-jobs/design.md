# Design

## Context

Los changes 0–3 dejaron el esqueleto FastAPI (`apps/api`), configuración centralizada (`core/config.py`), diagnóstico (`doctor`) y los módulos puros del pipeline (`ingest`, `transcribe`, `select`, `reframe`, `subtitles`, `render`) invocables por CLI. El hardware objetivo es un Apple Silicon M1 con 16 GB de RAM unificada y sin Redis ni Docker (`openspec/config.yaml`). Véase `proposal.md` para la motivación y el alcance.

## Goals / Non-Goals

**Goals:**
- Persistir el dominio base de `docs/architecture.md §7` sobre SQLite con migraciones versionadas desde el día uno (Alembic), dejando el esquema listo para añadir `campaign`, `social_account` y `publication` en changes 6–8 sin migraciones destructivas.
- Ejecutar trabajos de forma fiable en un proceso worker separado (`winclip worker`), garantizando 1 trabajo pesado (GPU/MLX/ffmpeg) a la vez, concurrencia ligera configurable, reintentos con backoff, cancelación y recuperación de huérfanos.
- Exponer una API REST + SSE segura (streaming multipart sin cargar archivos en RAM, Range requests, prevención de path traversal) y un OpenAPI con `operationId` estables para `add-web-ui-cards`.

**Non-Goals:**
- Crear todavía las tablas `campaign`, `social_account` ni `publication` (se agregan en changes 6, 7 y 8 mediante nuevas revisiones de Alembic).
- Implementar la interfaz web (`add-web-ui-cards`) o el handler real de publicación (`add-publishers`).
- Autenticación multi-usuario o almacenamiento S3 (se mantiene la interfaz `Storage` de `docs/architecture.md §8` para habilitarlo a futuro).

## Contratos

Contratos nuevos introducidos por este change (complementan `docs/architecture.md` sin contradecirlo):

### 1. Extensiones de esquema SQLite (sobre `docs/architecture.md §7`)
- `workspace`: `id` (ULID minúsculas), `name`, `created_at`. Al iniciar la API o el worker se garantiza idempotente un workspace por defecto (`DEFAULT_WORKSPACE_NAME="Default"`).
- `project`: columnas de §7 (`id`, `workspace_id`, `campaign_id` nullable sin FK aún, `source_type` `url|file`, `source_url?`, `title`, `status` `queued|processing|ready|failed|cancelled`, `requested_clips` `int | None` donde `NULL` representa `"max"`, `language` `auto|es|en`, `duration` `float | None`, `created_at`) más `subtitle_preset` (`str`, default `"bold-yellow"`), `reframe_mode` (`str`, default `"face"`), `source_path` (`str | None`, ruta relativa bajo `STORAGE_DIR`) y `updated_at`.
- `clip`: columnas de §7 (`id`, `project_id`, `candidate` JSON, `status` `draft|rendering|rendered|failed`, `title`, `description`, `hashtags` JSON `list[str]`, `score` `int`, `path` ruta relativa, `thumb_path` ruta relativa) más `hook` (`str`), `start_sec` (`float`), `end_sec` (`float`), `duration` (`float`), `created_at`, `updated_at`.
- `job`: columnas de §7 (`id`, `project_id?`, `type` `ingest|transcribe|select|render|pipeline|publish`, `payload` JSON, `status` `queued|running|done|failed|cancelled`, `progress` `0..100`, `stage` `str`, `error` `str | None`, `attempts` `int`, `created_at`, `started_at`, `finished_at`, `updated_at`) más `max_attempts` (`int`), `next_run_at` (`datetime | None`), `worker_id` (`str | None`), `heartbeat_at` (`datetime | None`), `heavy_active` (`bool`, default `False`), `cancel_requested` (`bool`, default `False`).
- `job_event` (tabla interna outbox para SSE entre procesos): `id` (`int` autoincrement PK), `project_id` (`str | None`), `job_id` (`str | None`), `event_type` (`job.progress|job.done|job.failed|clip.ready`), `payload` (JSON), `created_at`.

### 2. Endpoints REST y `operationId` estables

| Método y ruta | `operationId` | Resumen del contrato |
|---|---|---|
| `GET /api/health` | `getHealth` | Diagnóstico existente (change 0), añade `operationId` estable |
| `POST /api/projects` | `createProject` | Acepta `application/json` (URL) o `multipart/form-data` (archivo en streaming o URL). Campos: `source_type`, `source_url?`, `file?`, `title?`, `requested_clips` (`int \| "max"`), `language` (`auto\|es\|en`), `campaign_id?`, `subtitle_preset?`, `reframe_mode?`. Responde `201` con `{project, job}` |
| `GET /api/projects` | `listProjects` | Lista ordenada por `created_at DESC` con `clips_count`, `thumb_url?`, `active_job?` (`id`, `status`, `progress`, `stage`, `error`) |
| `GET /api/projects/{project_id}` | `getProject` | Detalle de proyecto con `clips_count`, `thumb_url?` y `latest_job?` / lista de `jobs` |
| `DELETE /api/projects/{project_id}` | `deleteProject` | Cancela jobs activos, borra DB + `storage/projects/<id>`, responde `204` |
| `GET /api/projects/{project_id}/clips` | `listProjectClips` | Lista de clips del proyecto ordenados por `score DESC` con `video_url` y `thumb_url` |
| `PATCH /api/clips/{clip_id}` | `updateClip` | Actualiza parcialmente `title`, `description`, `hashtags`, `start_sec`, `end_sec` (`0 <= start_sec < end_sec`; actualiza también `candidate` JSON y `duration`) |
| `DELETE /api/clips/{clip_id}` | `deleteClip` | Borra registro del clip y `storage/projects/<project_id>/clips/<clip_id>`, responde `204` |
| `POST /api/clips/{clip_id}/rerender` | `rerenderClip` | Encola trabajo `render` para el clip y responde `202` con el `Job` creado |
| `GET /api/clips/{clip_id}/file` | `getClipFile` | Video MP4 con `Accept-Ranges: bytes` y `206 Partial Content` si llega cabecera `Range` |
| `GET /api/clips/{clip_id}/thumb` | `getClipThumb` | Miniatura JPEG con soporte `Range` y `Cache-Control` |
| `GET /api/presets` | `listSubtitlePresets` | Catálogo de presets leídos desde `assets/subtitle-presets/*.json` |
| `GET /api/jobs/{job_id}` | `getJob` | Estado completo de un trabajo |
| `POST /api/jobs/{job_id}/cancel` | `cancelJob` | Cancela un trabajo `queued` o `running` (`200`); `409` si ya es terminal |
| `GET /api/events` | `streamEvents` | SSE `text/event-stream`, query opcional `project_id` y cabecera opcional `Last-Event-ID` |

### 3. Esquema de eventos SSE (`GET /api/events`)
- `event: job.progress` → `{"job_id", "project_id", "type", "status", "progress", "stage"}`
- `event: job.done` → `{"job_id", "project_id", "type", "status": "done", "progress": 100, "stage": "done"}`
- `event: job.failed` → `{"job_id", "project_id", "type", "status": "failed", "stage", "error"}`
- `event: clip.ready` → `{"project_id", "job_id", "clip_id", "status": "rendered", "thumb_url", "video_url"}`
- `event: heartbeat` → `{"ts": "<iso8601>"}` (cada 15 s)

### 4. Variables de entorno opcionales (defaults en `core/config.py` y `.env.example`)
- `WORKER_LIGHT_CONCURRENCY` (default `2`): máximo de trabajos ligeros simultáneos por worker.
- `WORKER_POLL_INTERVAL` (default `1.0`): segundos entre sondeos de cola cuando está vacía.
- `JOB_MAX_ATTEMPTS` (default `3`): reintentos máximos por trabajo.
- `JOB_STALE_SECONDS` (default `300`): umbral sin latido para considerar un trabajo huérfano.
- `UPLOAD_MAX_BYTES` (default `10737418240`, 10 GiB): límite máximo de carga multipart.
- `SSE_HEARTBEAT_SECONDS` (default `15`): intervalo de `heartbeat` SSE.

### 5. Rutas adicionales en `apps/api/winclip/routers/`
Se añaden `routers/jobs.py` y `routers/presets.py` junto a `projects.py`, `clips.py` y `events.py` (extensión aditiva a `docs/architecture.md §3`).

## Decisions

1. **Alembic desde el inicio con `render_as_batch=True` en SQLite.**
   - *Por qué:* aunque hoy hay una sola base local, los changes 6, 7 y 8 añadirán `campaign`, `social_account`, `publication` y claves foráneas sobre tablas existentes, y el objetivo futuro es migrar a PostgreSQL en un SaaS. `SQLModel.metadata.create_all()` no gestiona alteraciones de esquema ni claves foráneas en SQLite; Alembic con modo batch resuelve `ALTER TABLE` en SQLite y prepara la migración limpia a Postgres.
   - *Alternativa descartada:* `create_all()` sin migraciones (rompería bases locales existentes al avanzar a los changes 6–8 y obligaría a recrear el esquema más adelante).
   - *Dependencia nueva:* `alembic` (estándar sobre SQLAlchemy, mismo ecosistema que SQLModel).

2. **SQLite en modo WAL (`journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON`).**
   - *Por qué:* la API y el worker son procesos distintos accediendo a `storage/winclip.db` concurrentemente. WAL permite lecturas concurrentes sin bloquear al escritor y `busy_timeout` absorbe contenciones breves.
   - *Alternativa descartada:* modo journal rollback por defecto (produce `database is locked` frecuente entre API y worker).

3. **Reclamo atómico con `BEGIN IMMEDIATE` + `UPDATE ... RETURNING` y flag `heavy_active`.**
   - *Por qué:* SQLite 3.43 (incluido en Python 3.12) soporta `RETURNING`. En una transacción `BEGIN IMMEDIATE`, el worker comprueba si existe algún trabajo con `status='running' AND heavy_active=1` antes de reclamar un `transcribe`/`render` o antes de que un `pipeline` entre en sus fases pesadas (`transcribe` y `render`). Así un `pipeline` en fase `ingest` o `select` no bloquea un `rerender`, pero nunca coinciden dos tareas GPU/MLX/ffmpeg en el M1 de 16 GB.
   - *Alternativa descartada:* lock por archivo en disco (`fcntl`), que no es atómico respecto al estado de la fila ni limpio en recuperación de huérfanos; o descomponer `pipeline` en 4 jobs hijos, que complica el seguimiento de un único `job_id` y el progreso continuo `0–100%` en la UI.

4. **Comunicación worker → API para SSE mediante tabla outbox `job_event` + broadcaster único en la API.**
   - *Por qué:* sin Redis ni broker externo, escribir eventos en `job_event` dentro de SQLite WAL es durable, simple y tolerante a reinicios de la API. Un único bucle `asyncio` en el lifespan de FastAPI lee `job_event WHERE id > last_id` cada ~400 ms y distribuye a colas en memoria por cliente SSE, soportando `Last-Event-ID` en reconexiones. El worker purga eventos con más de 24 h periódicamente.
   - *Alternativa descartada:* webhook HTTP worker → API (pierde eventos si la API está reiniciando); polling por cliente sobre la tabla `job` (multiplica consultas por pestaña y pierde eventos discretos como `clip.ready`).

5. **Subida de archivos grandes en streaming en `POST /api/projects` con `python-multipart`.**
   - *Por qué:* videos largos pueden pesar varios GB en local. Usar un parser multipart en streaming sobre `request.stream()` (mediante `python-multipart`) escribe los chunks directamente a `storage/projects/<project_id>/source/original.<ext>` validando extensión permitida y `UPLOAD_MAX_BYTES`, evitando duplicar archivos en `/tmp` o agotar los 16 GB de RAM. `POST /api/projects` inspecciona `Content-Type` (`application/json` o `multipart/form-data`) y declara ambos esquemas en `openapi_extra` para mantener un OpenAPI preciso.
   - *Alternativa descartada:* leer `await file.read()` en memoria (OOM en videos grandes) o crear un endpoint separado `/projects/upload` (contradice el contrato deseado de `POST /projects`).
   - *Dependencia nueva:* `python-multipart` (requerida oficialmente por FastAPI para `multipart/form-data`).

6. **Validación estricta de rutas en `Storage` + servicio HTTP Range.**
   - *Por qué:* todos los paths guardados en `clip.path` y `clip.thumb_path` son relativos a `STORAGE_DIR`. Antes de abrir cualquier archivo en `/file` o `/thumb`, `Storage.resolve_safe()` resuelve symlinks (`Path.resolve()`) y verifica `is_relative_to(storage_root)` rechazando `..`, rutas absolutas o escapes con `403`. El streaming Range parsea `bytes=start-end` (validando límites y devolviendo `416` si está fuera de rango) y transmite en chunks de 256 KiB.
   - *Alternativa descartada:* `StaticFiles` montado sobre `storage/` (expondría `accounts/`, `cache/llm/` y archivos intermedios sin control por clip).

7. **Justificación del resto de dependencias nuevas:**
   - `sqlmodel`: fijada en el stack (`openspec/config.yaml` y `docs/architecture.md §7`); unifica modelos SQLAlchemy y validación Pydantic v2.
   - `python-ulid`: genera ULIDs en minúsculas ordenables lexicográficamente por tiempo según `docs/architecture.md §5` (`core/ids.py`). Alternativa: `uuid4`, no ordenable cronológicamente y contrario a §5.

8. **Worker integrado en `pnpm dev` y CLI `winclip worker`.**
   - *Por qué:* en `package.json` raíz, `concurrently` lanza `api`, `web` y ahora `worker` (`uv run --project apps/api winclip worker`) con prefijos claros. El worker escucha `SIGINT`/`SIGTERM`, deja de reclamar jobs nuevos, espera brevemente la finalización limpia o cancela subprocesos y cierra conexiones.

## Risks / Trade-offs

- [Contención de escritura SQLite bajo progreso muy frecuente] → Limitar la escritura de `job.progress` (p. ej. solo cuando cambia >= 1% o de etapa, o cada >= 500 ms) y usar WAL + `busy_timeout=5000`.
- [Subproceso pesado (`ffmpeg` o `mlx-whisper`) no responde inmediatamente a cancelación] → El worker ejecuta un hilo/tarea de latido que comprueba `cancel_requested` cada 2 s y propaga un `threading.Event` / señal `SIGTERM` al subproceso hijo para detenerlo limpiamente.
- [Archivos temporales si se aborta una subida multipart a mitad] → Si ocurre desconexión o error de validación durante el streaming en `POST /api/projects`, un bloque `except`/`finally` elimina la carpeta parcial `storage/projects/<project_id>` antes de responder.
- [Desalineación de enum `reframe_mode` o estructura JSON de `assets/subtitle-presets/*.json` con el change 3] → Leer presets dinámicamente de disco aceptando campos flexibles y validar `reframe_mode` contra las constantes compartidas del módulo `pipeline/reframe.py` al integrarse tras el change 3.

## Migration Plan

1. Configurar Alembic en `apps/api/alembic/` leyendo `DATABASE_URL` desde `Settings` con `render_as_batch=True` cuando el dialecto sea SQLite.
2. Crear la migración inicial `0001_initial_core_tables` con las tablas `workspace`, `project`, `clip`, `job` y `job_event`, más índices sobre `job(status, next_run_at, created_at)`, `clip(project_id)` y `job_event(project_id, id)`.
3. Ejecutar `alembic upgrade head` en el arranque de desarrollo/CLI (`winclip db upgrade` o en startup de `api`/`worker` bajo lock) y asegurar idempotencia del workspace por defecto.
4. Rollback: `alembic downgrade base` en entornos locales (sin datos previos en cambios 0–3).
