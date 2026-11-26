# Proposal

## Why

Los changes 1–3 entregan el pipeline de clipping únicamente por CLI, sin persistencia de estado ni ejecución asíncrona. Para conectar la interfaz web y preparar la gestión de campañas y publicaciones sin bloquear peticiones HTTP ni saturar la GPU del M1, hace falta una capa de base de datos, una cola de trabajos persistente con worker separado y una API REST + SSE con contrato OpenAPI estable.

## What Changes

- Capa de persistencia en SQLite (`storage/winclip.db`) con SQLModel y migraciones versionadas con Alembic desde el inicio, cubriendo las entidades base de `docs/architecture.md §7` (`workspace` con creación idempotente del workspace por defecto al arrancar, `project`, `clip` y `job`, manteniendo `campaign_id` opcional para el change 6).
- Cola persistente sobre la tabla `jobs` soportando los tipos `ingest`, `transcribe`, `select`, `render`, `pipeline` (encadenamiento completo) y `publish` (reservado para el change 8).
- Worker en proceso separado (`winclip worker`), integrado también en `pnpm dev`: reclamo atómico de trabajos, exclusión mutua para trabajos pesados (`transcribe`, `render` y fases pesadas de `pipeline`), concurrencia configurable para trabajos ligeros, reintentos con backoff exponencial, cancelación cooperativa, persistencia de progreso/etapa y recuperación automática de trabajos huérfanos al reiniciar.
- API REST bajo `/api`:
  - Proyectos: `POST /api/projects` (URL o subida multipart grande en streaming; `requested_clips` entero o `"max"`, `language`, `campaign_id` opcional, `subtitle_preset`, `reframe_mode`), `GET /api/projects`, `GET /api/projects/{id}`, `DELETE /api/projects/{id}`.
  - Clips: `GET /api/projects/{id}/clips`, `PATCH /api/clips/{id}` (título, descripción, hashtags, `start`/`end`), `DELETE /api/clips/{id}`, `POST /api/clips/{id}/rerender`, `GET /api/clips/{id}/file` y `GET /api/clips/{id}/thumb` con soporte HTTP `Range` y protección contra path traversal.
  - Presets: `GET /api/presets` (lectura del catálogo `assets/subtitle-presets/*.json` para el frontend).
  - Trabajos y eventos: `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel` y `GET /api/events` (SSE con `job.progress`, `job.done`, `job.failed`, `clip.ready` y `heartbeat`).
- Esquema OpenAPI con `operationId` explícitos y estables en todas las rutas para generar `packages/api-client` en el change 5.

**Fuera de alcance:** interfaz web de dashboard y revisión de cards (`add-web-ui-cards`), tablas y endpoints de campañas (`add-campaign-rules`), cuentas sociales (`add-social-accounts`), ejecución real de trabajos `publish` (`add-publishers`), autenticación/multi-tenant activo y sistemas externos de colas o contenedores (Redis, Celery, Docker).

## Capabilities

### New Capabilities
- `job-queue`: persistencia de trabajos y entidades base, cola duradera en SQLite y worker independiente con control de concurrencia pesada/ligera, reintentos con backoff, cancelación y recuperación de huérfanos.
- `projects-api`: API REST y stream SSE para crear y administrar proyectos, clips, trabajos, presets de subtítulos y descarga segura de archivos multimedia con contrato OpenAPI estable.

### Modified Capabilities

## Impact

- Código nuevo y modificado en `apps/api`: `winclip/core/{db.py,models.py,ids.py,storage.py,config.py}`, `apps/api/alembic/`, `winclip/worker/{queue.py,runner.py,handlers.py}`, `winclip/routers/{projects.py,clips.py,jobs.py,events.py,presets.py}`, `winclip/main.py`, `winclip/cli.py`, `apps/api/tests/`.
- Raíz del monorepo: `package.json` (`pnpm dev` añade el proceso `worker`), `.env.example`, `README.md`.
- Nuevas dependencias Python en `apps/api/pyproject.toml`: `sqlmodel`, `alembic`, `python-ulid`, `python-multipart`.
