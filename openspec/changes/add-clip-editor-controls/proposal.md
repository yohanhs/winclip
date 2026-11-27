# Proposal

## Why

Cuando Whisper transcribe un video largo, es habitual que aparezcan errores puntuales en nombres propios, marcas o tecnicismos; además, dentro de un mismo proyecto puede convenir aplicar un preset de subtítulos o modo de reencuadre distinto a un clip concreto (por ejemplo `blur` en una gráfica mientras el resto usa `face`), o afinar manualmente el encuadre (`crop_x_pct`, `crop_y_pct`, `zoom_pct`). Permitir estos tres ajustes por clip desde la web evita tener que exportar y re-editar en herramientas externas como CapCut.

## What Changes

- **Corrección de subtítulos por clip:** endpoint `GET /api/clips/{id}/words` para leer las palabras del clip (con timestamps originales desde `transcript.json` y sus overrides guardados) y soporte en `PATCH /api/clips/{id}` para persistir `subtitle_overrides` (texto corregido por índice de palabra, sin alterar timestamps) que el motor de subtítulos aplica al re-renderizar.
- **Overrides de render por clip:** soporte en `PATCH /api/clips/{id}` y `POST /api/clips/{id}/rerender` para sobrescribir `subtitle_preset`, `reframe_mode` (`face`, `center`, `blur`, `passthrough`) y parámetros manuales de cámara (`crop_x_pct`, `crop_y_pct`, `zoom_pct`) por clip individual sin modificar los ajustes del resto del proyecto.
- **Editor ampliado en la web (`apps/web`):** dentro del diálogo de edición/recorte de cada clip (`/projects/[id]`), pestañas o secciones para (1) editar palabras de subtítulos inline con reseteo al texto original, (2) elegir preset de subtítulos y modo de reencuadre por clip con vista previa, y (3) ajustar `crop_x`, `crop_y` y `zoom` cuando el modo es `center`, disparando el re-render con actualización SSE automática.
- Regeneración de `packages/api-client` desde OpenAPI y pruebas unitarias/integración en backend y frontend.

**Fuera de alcance:** edición multipista tipo CapCut (música de fondo, B-roll, cortes intermedios, transiciones, stickers), edición manual de timestamps palabra a palabra y cambio masivo entre múltiples proyectos.

## Capabilities

### New Capabilities
- `clip-editor-controls`: edición por clip de palabras de subtítulos, preset de subtítulos, modo de reencuadre y recorte manual (`crop_x_pct`, `crop_y_pct`, `zoom_pct`), persistidos en el clip y aplicados en el re-renderizado.

### Modified Capabilities

## Impact

- Backend (`apps/api`): migración Alembic opcional o campo JSON `render_overrides` / `subtitle_overrides` en `clip`, extensión de `routers/clips.py`, `routers/schemas.py`, `worker/handlers.py` y `pipeline/render.py` (`subtitles/layout.py`).
- Cliente y frontend (`packages/api-client`, `apps/web`): `pnpm gen:api`, extensión de `clip-trim-dialog.tsx` / `clip-edit-dialog.tsx`, nuevos componentes `subtitle-word-editor.tsx` y `crop-controls.tsx`, tests Vitest y cobertura E2E.
- Sin dependencias nuevas en Python ni JS.
