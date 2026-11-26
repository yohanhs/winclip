# Tasks

## 1. Base de datos, modelos SQLModel y migraciones Alembic

- [ ] 1.1 Añadir dependencias `sqlmodel`, `alembic`, `python-ulid` y `python-multipart` en `apps/api/pyproject.toml`, más variables opcionales del worker/upload/SSE en `winclip/core/config.py` y `.env.example`. Verificar con `uv run --project apps/api python -c "import sqlmodel, alembic, ulid, multipart"` y test unitario de defaults en `config.py`.
- [ ] 1.2 Implementar `winclip/core/ids.py` (generación y validación de ULID en minúsculas) y extender `winclip/core/storage.py` con rutas por proyecto y `resolve_safe()` anti path traversal. Verificar con tests unitarios en `tests/test_storage_ids.py` cubriendo ULIDs válidos y rechazos de `../`, rutas absolutas y symlinks fuera de `STORAGE_DIR`.
- [ ] 1.3 Implementar `winclip/core/models.py` (`Workspace`, `Project`, `Clip`, `Job`, `JobEvent`) y `winclip/core/db.py` (engine SQLite con WAL, `busy_timeout=5000`, `foreign_keys=ON`, sesión y seed idempotente del workspace por defecto). Verificar con tests en `tests/test_db_models.py` comprobando creación idempotente del workspace y relaciones proyecto–clips–jobs.
- [ ] 1.4 Inicializar Alembic en `apps/api/alembic/` (`render_as_batch=True`, lectura de `DATABASE_URL` desde `Settings`) y generar la revisión inicial `0001_initial_core_tables` con índices de cola y eventos. Verificar ejecutando `alembic upgrade head` y `alembic downgrade base && alembic upgrade head` sobre una SQLite temporal en un test de migración.

## 2. Cola persistente y worker independiente

- [ ] 2.1 Implementar `winclip/worker/queue.py` con operaciones atómicas (`BEGIN IMMEDIATE`): encolado, reclamo atómico respetando `heavy_active` (1 trabajo pesado a la vez) y concurrencia ligera configurable, actualización de progreso/etapa, registro de `JobEvent`, backoff exponencial en reintentos, solicitud de cancelación y recuperación de trabajos huérfanos por `heartbeat_at`. Verificar con `pytest tests/test_job_queue.py` cubriendo concurrencia pesada/ligera, doble reclamo con hilos concurrentes, reintentos/backoff, cancelación y recuperación de huérfanos.
- [ ] 2.2 Implementar `winclip/worker/handlers.py` conectando los tipos `ingest`, `transcribe`, `select`, `render`, `pipeline` (encadenando fases con adquisición/liberación de `heavy_active`, checkpoints de cancelación, creación de clips y emisión de `clip.ready`) y `publish` (fallo controlado sin reintentos indicando estado reservado). Verificar con `pytest tests/test_worker_handlers.py` usando mocks del pipeline para validar transiciones de etapa, creación de clips, cancelación en mitad del pipeline y rechazo de `publish`.
- [ ] 2.3 Implementar `winclip/worker/runner.py` (bucle principal con pool de trabajos ligeros, hilo de latido/heartbeat, recuperación de huérfanos al iniciar, purga de eventos antiguos y apagado limpio con `SIGINT`/`SIGTERM`), registrar `winclip worker` en `winclip/cli.py` y añadir el proceso `worker` a `pnpm dev` en `package.json` raíz (documentándolo en `README.md`). Verificar con un test de integración del runner (`tests/test_worker_runner.py`) que procesa un trabajo encolado en SQLite y se detiene limpiamente al recibir señal.

## 3. API REST de proyectos, clips, presets y trabajos

- [ ] 3.1 Implementar esquemas de petición/respuesta Pydantic y `winclip/routers/projects.py` (`POST /api/projects` soportando JSON para URL y streaming multipart chunked para archivos grandes con limpieza en fallo, `GET /api/projects`, `GET /api/projects/{id}`, `DELETE /api/projects/{id}` con cancelación y borrado en disco) con `operationId` explícitos. Verificar con `pytest tests/test_api_projects.py` cubriendo URL, subida multipart en streaming, validaciones 400/422, 404 y borrado completo.
- [ ] 3.2 Implementar `winclip/routers/clips.py` (`GET /api/projects/{id}/clips`, `PATCH /api/clips/{id}`, `DELETE /api/clips/{id}`, `POST /api/clips/{id}/rerender`, `GET /api/clips/{id}/file`, `GET /api/clips/{id}/thumb` con soporte HTTP `Range` 206/416 y verificación anti path traversal) con `operationId` explícitos. Verificar con `pytest tests/test_api_clips.py` cubriendo edición de metadatos y tiempos, validación `start < end`, re-render 202, borrado 204, peticiones `Range` y bloqueo de path traversal.
- [ ] 3.3 Implementar `winclip/routers/jobs.py` (`GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel` con `409` en estados terminales) y `winclip/routers/presets.py` (`GET /api/presets` leyendo `assets/subtitle-presets/*.json`), asegurando `operationId` explícitos en todos los routers (incluyendo `GET /api/health`) y registrándolos en `winclip/main.py`. Verificar con `pytest tests/test_api_jobs_presets.py` y un test que inspeccione `/openapi.json` validando unicidad y estabilidad de todos los `operationId`.

## 4. Eventos SSE en tiempo real

- [ ] 4.1 Implementar el broadcaster compartido sobre `job_event` (en el lifespan de `winclip/main.py`) y `winclip/routers/events.py` (`GET /api/events` con filtro opcional `project_id`, soporte `Last-Event-ID`, emisión de `job.progress`, `job.done`, `job.failed`, `clip.ready` y `heartbeat` periódico, y limpieza al desconectar). Verificar con `pytest tests/test_api_events.py` validando recepción de eventos filtrados por proyecto, `heartbeat` y desconexión limpia.
- [ ] 4.2 Documentar endpoints REST, flujo del worker y eventos SSE en `README.md` (o `docs/api.md` enlazado desde `README.md`). Verificar que los comandos documentados (`winclip worker`, `pnpm dev`, `GET /api/health`) coinciden con la implementación real.

## 5. Verificación integrada

- [ ] 5.1 Ejecutar prueba integrada de extremo a extremo (API + worker contra SQLite temporal con pipeline mockeado: crear proyecto → seguir SSE hasta `clip.ready` y `job.done` → editar clip → solicitar `rerender` → servir archivo con `Range` → eliminar proyecto), ejecutar `uv run --project apps/api ruff check . && uv run --project apps/api ruff format --check . && uv run --project apps/api pytest` y ejecutar `openspec validate add-api-jobs --strict` sin errores.

## Workflow follow-up

- Revisión del orquestador y merge de la rama `change/add-api-jobs` en `main`.
- Archivar el change con `openspec archive add-api-jobs` una vez aprobado.
