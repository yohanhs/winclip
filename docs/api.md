# API local, cola de trabajos y eventos SSE

Contratos del change `add-api-jobs` (capabilities `projects-api` y `job-queue`). Complementan
`docs/architecture.md` sin contradecirlo.

## Arranque

```bash
pnpm dev                                  # API :8000 + worker + web :3000
uv run --project apps/api winclip worker  # solo el worker (procesa la cola)
uv run --project apps/api winclip db upgrade
```

La API y el worker aplican las migraciones de Alembic al arrancar (bajo un lock en `STORAGE_DIR`)
y garantizan el workspace por defecto. La base vive en `DATABASE_URL`, que por defecto se deriva
como `sqlite:///{STORAGE_DIR}/winclip.db`.

`pnpm dev` lanza tres procesos con `concurrently`: `api` (uvicorn con `--reload --reload-dir
apps/api`), `worker` y `web`. El worker se apaga de forma limpia con `SIGINT`/`SIGTERM`: deja de
reclamar trabajos, espera hasta 10 s a los que están en curso y solicita cancelación a los que
sigan vivos.

## Endpoints

Todas las operaciones bajo `/api` declaran un `operationId` estable para generar
`packages/api-client` en el change 5 (verificado en `/openapi.json`).

| Método y ruta | `operationId` | Respuesta |
|---|---|---|
| `GET /api/health` | `getHealth` | Diagnóstico (`ok`/`warn`/`error`) |
| `POST /api/projects` | `createProject` | `201 {project, job}` |
| `GET /api/projects` | `listProjects` | Proyectos recientes primero |
| `GET /api/projects/{project_id}` | `getProject` | Detalle con `jobs` |
| `DELETE /api/projects/{project_id}` | `deleteProject` | `204` (cancela jobs y borra archivos) |
| `GET /api/projects/{project_id}/clips` | `listProjectClips` | Clips por `score` descendente |
| `PATCH /api/clips/{clip_id}` | `updateClip` | Clip actualizado |
| `DELETE /api/clips/{clip_id}` | `deleteClip` | `204` |
| `POST /api/clips/{clip_id}/rerender` | `rerenderClip` | `202 Job` |
| `GET /api/clips/{clip_id}/file` | `getClipFile` | MP4 con `Accept-Ranges` y `206` |
| `GET /api/clips/{clip_id}/thumb` | `getClipThumb` | JPEG con caché y `206` |
| `GET /api/presets` | `listSubtitlePresets` | Presets de `assets/subtitle-presets/*.json` |
| `GET /api/jobs/{job_id}` | `getJob` | Estado completo del trabajo |
| `POST /api/jobs/{job_id}/cancel` | `cancelJob` | `200` o `409` si ya terminó |
| `GET /api/events` | `streamEvents` | SSE `text/event-stream` |

### Crear un proyecto

```bash
# URL (JSON)
curl -s -X POST http://127.0.0.1:8000/api/projects \
  -H 'content-type: application/json' \
  -d '{"source_url":"https://www.youtube.com/watch?v=...","requested_clips":5,
       "language":"es","subtitle_preset":"bold-yellow","reframe_mode":"face"}'

# Archivo grande (multipart, se escribe en streaming en source/original.<ext>)
curl -s -X POST http://127.0.0.1:8000/api/projects \
  -F 'file=@video.mp4' -F 'requested_clips=max' -F 'language=auto'
```

- `requested_clips`: entero `>= 1` o `"max"` (`null` en las respuestas).
- `language`: `auto | es | en`.
- `reframe_mode`: `face | center | blur | passthrough` (los mismos valores de
  `pipeline/reframe.py`; `passthrough` solo aplica a fuentes ya verticales).
- `subtitle_preset`: cualquier id de `assets/subtitle-presets/` (`bold-yellow`, `hormozi`,
  `clean-white`, `mrbeast`); un preset inexistente responde `422`.
- `UPLOAD_MAX_BYTES` (10 GiB por defecto) limita el cuerpo multipart (`413`). Un fallo a mitad
  elimina la carpeta parcial del proyecto: no quedan archivos huérfanos.
- La respuesta incluye el trabajo `pipeline` en estado `queued`.

`PATCH /api/clips/{id}` acepta `title`, `description`, `hashtags`, `start_sec` y `end_sec`; exige
`0 <= start_sec < end_sec` (`422` en caso contrario) y mantiene sincronizado el `candidate` JSON.
`POST .../rerender` reescribe antes `selection/candidates.json` con los tiempos editados del clip,
así que el re-render usa lo que se ve en la UI.

### Descarga con Range

```bash
curl -s -D - -o clip.part \\
  -H 'Range: bytes=0-1023' http://127.0.0.1:8000/api/clips/<clip_id>/file
# 206 Partial Content, Content-Range: bytes 0-1023/<size>, Accept-Ranges: bytes
```

Rangos fuera del archivo o malformados responden `416` con `Content-Range: bytes */<size>`.
Las rutas guardadas en `clip.path`/`clip.thumb_path` se resuelven con `Storage.resolve_safe()`
(symlinks incluidos); cualquier escape de `STORAGE_DIR` responde `403`.

## Cola de trabajos

Tipos: `ingest`, `transcribe`, `select`, `render`, `pipeline` y `publish` (reservado: falla sin
reintentos hasta el change 8).

- `pipeline` encadena ingesta → transcripción → selección → render en un único `job_id`, con
  progreso `0–100` y etapas persistidas (`job.progress`, `job.stage`).
- Un solo trabajo pesado a la vez (`transcribe`, `render` y las fases pesadas de `pipeline`); los
  ligeros usan `WORKER_LIGHT_CONCURRENCY` hilos. El reclamo es un único `UPDATE … RETURNING`, así
  que dos workers nunca toman la misma fila.
- Reintentos con backoff exponencial (2 s, 4 s, 8 s… hasta 300 s) y `JOB_MAX_ATTEMPTS`;
  al agotarlos el trabajo pasa a `failed` y el proyecto también.
- Cancelación: un trabajo `queued` pasa a `cancelled` al instante; uno `running` recibe
  `cancel_requested` y el worker lo interrumpe en el siguiente punto seguro, liberando el bloqueo
  pesado.
- Al arrancar, los trabajos `running` con latido más antiguo que `JOB_STALE_SECONDS` vuelven a
  `queued` (o a `failed` si agotaron intentos).

Variables nuevas (`.env.example`): `WORKER_LIGHT_CONCURRENCY`, `WORKER_POLL_INTERVAL`,
`JOB_MAX_ATTEMPTS`, `JOB_STALE_SECONDS`, `UPLOAD_MAX_BYTES`, `SSE_HEARTBEAT_SECONDS`.

## Eventos SSE

`GET /api/events?project_id=<id>` (opcional) y cabecera opcional `Last-Event-ID`. El worker escribe
en la tabla outbox `job_event`; un único bucle en el lifespan de la API la lee cada ~400 ms y
reparte los eventos a las conexiones vivas.

```
id: 42
event: job.progress
data: {"job_id":"…","project_id":"…","type":"pipeline","status":"running","progress":42.0,"stage":"transcribe"}

event: heartbeat
data: {"ts":"2026-11-26T18:00:00+00:00"}
```

- `job.progress`: `{job_id, project_id, type, status, progress, stage}`
- `job.done`: `{job_id, project_id, type, status:"done", progress:100, stage:"done"}`
- `job.failed`: `{job_id, project_id, type, status:"failed", stage, error}`
- `clip.ready`: `{project_id, job_id, clip_id, status:"rendered", thumb_url, video_url}`
- `heartbeat` cada `SSE_HEARTBEAT_SECONDS` (15 s por defecto), sin `id`.

Reconectar con `Last-Event-ID: <último id>` reentrega solo lo posterior. Los eventos de más de 24 h
se purgan periódicamente desde el worker.

```bash
curl -N 'http://127.0.0.1:8000/api/events?project_id=<id>'
```
