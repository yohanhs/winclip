# Tasks

## 1. Modelo de datos y contratos de API

- [x] 1.1 Añadir columnas JSON `render_overrides` y `subtitle_overrides` a `Clip` en `apps/api/winclip/core/models.py` y crear la migración Alembic correspondiente (`render_as_batch=True` en SQLite). Verificar ejecutando `alembic upgrade head` y `alembic downgrade -1 && alembic upgrade head` en tests de migración.
- [x] 1.2 Extender `ClipUpdate`, `ClipOut` y añadir `ClipWordOut` / `ClipWordsOut` en `apps/api/winclip/routers/schemas.py` con validaciones (`subtitle_preset` contra catálogo de `assets/subtitle-presets/`, `reframe_mode` en `face|center|blur|passthrough`, `0 <= crop_x_pct <= 100`, `0 <= crop_y_pct <= 100`, `50 <= zoom_pct <= 200`, y longitud <= 64 chars por palabra corregida). Verificar con tests unitarios de validación en `apps/api/tests/test_clip_editor_api.py`.
- [x] 1.3 Implementar `GET /api/clips/{id}/words` (`operationId="getClipWords"`) y ampliar `PATCH /api/clips/{id}` en `apps/api/winclip/routers/clips.py` persistiendo `render_overrides` y `subtitle_overrides` (clave estable `start_ms:end_ms`). Verificar con `uv run --project apps/api pytest tests/test_clip_editor_api.py` cubriendo lectura, guardado, reseteo y rechazos 404/422.

## 2. Integración en subtítulos, render y worker

- [x] 2.1 Soportar `word_overrides: dict[str, str] | None` en `apps/api/winclip/pipeline/subtitles/layout.py` y propagarlo desde `pipeline/render.py` (incluyéndolo en el hash `.render.sha256` de idempotencia) sin modificar `transcript.json`. Verificar con tests unitarios en `apps/api/tests/test_subtitles_overrides.py` comprobando preservación de timestamps, `.ass` actualizado y disparo de re-render al cambiar una palabra.
- [x] 2.2 Actualizar `apps/api/winclip/worker/handlers.py` para resolver las opciones de render en cascada (`clip.render_overrides` > campaña > proyecto) y pasar `word_overrides`, `preset`, `reframe`, `crop_x_pct`, `crop_y_pct` y `zoom_pct` a `render_clip`. Verificar con tests en `apps/api/tests/test_worker_clip_overrides.py` comprobando aislamiento entre clips del mismo proyecto.

## 3. Cliente tipado e interfaz web

- [x] 3.1 Regenerar `packages/api-client` con `pnpm gen:api` y añadir el hook `useClipWords` (y mutación ampliada en `use-clips.ts`) en `apps/web/hooks/`. Verificar con `pnpm --filter @winclip/api-client typecheck && pnpm --filter web typecheck`.
- [x] 3.2 Crear `apps/web/components/projects/subtitle-word-editor.tsx` (edición inline de palabras con indicador visual de editada y botón `"Restablecer texto"`) y `apps/web/components/projects/crop-controls.tsx` (selectores de `subtitle_preset` y `reframe_mode`, más sliders `crop_x_pct`, `crop_y_pct` y `zoom_pct` visibles en modo `center`), siguiendo `docs/ui-design.md`. Verificar con tests en `apps/web/tests/clip-editor-controls.test.tsx`.
- [x] 3.3 Integrar las pestañas `Recorte y metadatos`, `Subtítulos` y `Cámara / Estilo` en el editor de clips (`clip-trim-dialog.tsx` / `project-detail.tsx`) conectadas a `PATCH /api/clips/{id}` + `POST /api/clips/{id}/rerender` con actualización SSE y cache-busting, y actualizar `README.md`. Verificar con tests en `apps/web/tests/clip-trim.test.tsx` y un caso E2E en `apps/web/e2e/project-detail.spec.ts`.

## 4. Verificación integrada

- [x] 4.1 Ejecutar la suite completa: `uv run --project apps/api ruff check apps/api && uv run --project apps/api ruff format --check apps/api && uv run --project apps/api pytest apps/api/tests -m "not slow"`, `pnpm --filter @winclip/api-client typecheck && pnpm --filter web lint && pnpm --filter web typecheck && pnpm --filter web test && pnpm --filter web build && pnpm --filter web test:e2e`, y `openspec validate add-clip-editor-controls --strict` sin errores.

## Workflow follow-up

- Revisión del orquestador y prueba manual en local corrigiendo una palabra y ajustando `crop/zoom` sobre un clip real.
- Archivar el change con `openspec archive add-clip-editor-controls` tras la aprobación.
