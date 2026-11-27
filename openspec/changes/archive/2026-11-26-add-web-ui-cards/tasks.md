# Tasks

## 1. Cliente API tipado (`packages/api-client`) y entorno de tests web

- [x] 1.1 Configurar `packages/api-client` (`@winclip/api-client`) con `openapi-typescript` y `openapi-fetch`, añadir el script `gen:api` en el `package.json` raíz (exportando el esquema OpenAPI desde `apps/api` y generando `src/schema.d.ts`), implementar `src/client.ts` (`createApiClient` + `uploadProjectWithProgress` con `XMLHttpRequest` y `AbortSignal`) y enlazarlo como dependencia workspace en `apps/web`. Verificar ejecutando `pnpm gen:api` y `pnpm --filter @winclip/api-client build` (o `tsc --noEmit`) sin errores ni `any`.
- [x] 1.2 Configurar el tema oscuro moderno por defecto, `sonner` (Toaster global) y los componentes `shadcn/ui` necesarios (`card`, `badge`, `tabs`, `slider`, `switch`, `select`, `dialog`, `input`, `textarea`, `checkbox`, `progress`, `skeleton`, `tooltip`, `alert-dialog`) en `apps/web`. Verificar con `pnpm --filter web lint && pnpm --filter web build`.
- [x] 1.3 Configurar Vitest + Testing Library (`vitest.config.ts`, `jsdom`, setup de `jest-dom`) y MSW (`tests/mocks/handlers.ts`, fixtures tipados) en `apps/web`, más los hooks base `use-api-client.ts`, `use-projects.ts`, `use-clips.ts` y `use-project-events.ts` (SSE + actualización de caché TanStack Query). Verificar ejecutando `pnpm --filter web test` con tests unitarios de `use-project-events` cubriendo `job.progress`, `clip.ready`, `job.done` y `job.failed`.

## 2. Listado y creación de proyectos (`/projects` y `/projects/new`)

- [x] 2.1 Implementar `/projects` (`project-list.tsx`, `project-card.tsx`) mostrando estado, miniatura o placeholder, conteo de clips, barra de progreso en vivo vía SSE, diálogo de confirmación para eliminar proyecto y estados vacío/cargando/error con reintento. Verificar con tests Vitest + Testing Library en `tests/projects-list.test.tsx` cubriendo estados vacío, cargando, error, actualización en vivo y eliminación.
- [x] 2.2 Implementar `file-dropzone.tsx` (drag & drop, validación de tipo/tamaño, barra de progreso porcentual y cancelación) y `subtitle-preset-preview.tsx` (render visual karaoke en vivo consumiendo `GET /api/presets`). Verificar con tests en `tests/project-create-widgets.test.tsx` comprobando selección de archivo, actualización de preview al cambiar preset y validación de formato inválido.
- [x] 2.3 Implementar `/projects/new` (`project-create-form.tsx`) con pestañas `URL | Subir archivo`, slider de cantidad + toggle `"Máximo posible"` (`"max"`), idioma (`auto`, `es`, `en`), selector de campaña visible y deshabilitado con nota explicativa, selector de preset con preview, selector de modo de reframe, toasts y redirección a `/projects/[id]`. Verificar con tests en `tests/project-create-form.test.tsx` cubriendo flujo URL, flujo archivo con progreso, modo `"max"` y errores de validación/API.

## 3. Vista de detalle de proyecto y cards 9:16 (`/projects/[id]`)

- [x] 3.1 Implementar `pipeline-stepper.tsx` (4 etapas: Descarga, Transcripción, Selección, Render, porcentaje en vivo por SSE, botón cancelar trabajo con confirmación y banner de error en `job.failed`) e integrarlo en la cabecera de `/projects/[id]`. Verificar con tests en `tests/pipeline-stepper.test.tsx` cubriendo transiciones por etapa, cancelación y estado fallido.
- [x] 3.2 Implementar `clip-grid.tsx`, `clip-card.tsx` (aspecto 9:16, miniatura + `hover-play` silenciado, score, título, hook, duración formateada, hashtags, estados cargando/vacío/re-renderizando) y `clip-player-dialog.tsx` (reproducción con audio y controles). Verificar con tests en `tests/clip-card.test.tsx` comprobando renderizado de metadatos, comportamiento `hover-play` (play/pause) y apertura del reproductor.
- [x] 3.3 Implementar `clip-edit-dialog.tsx` (edición de `title`, `description`, `hashtags` vía `PATCH /api/clips/{id}` con toast), descarga directa del MP4 y diálogo de confirmación para `DELETE /api/clips/{id}`. Verificar con tests en `tests/clip-actions.test.tsx` cubriendo edición exitosa, error de API, enlace de descarga y eliminación.
- [x] 3.4 Implementar `mini-timeline.tsx` y `clip-trim-dialog.tsx` (ajuste interactivo de `start` y `end` dentro de la duración fuente, validación `0 <= start < end`, guardado con `PATCH /api/clips/{id}` y re-render con `POST /api/clips/{id}/rerender` actualizando la card al llegar `clip.ready` con cache-busting). Verificar con tests en `tests/clip-trim.test.tsx` cubriendo validación de rango inválido y disparo de re-render.
- [x] 3.5 Implementar multiselección en `clip-grid.tsx` y `selection-action-bar.tsx` (checkbox por card, seleccionar todos/limpiar, contador y botón `"Publicar"` deshabilitado con tooltip informativo hasta el change 8). Verificar con tests en `tests/clip-selection.test.tsx` comprobando selección múltiple, limpiar selección y estado deshabilitado de `"Publicar"`.

## 4. Tests E2E con Playwright + MSW, CI y documentación

- [x] 4.1 Configurar Playwright en `apps/web` (`playwright.config.ts`) con mocks MSW/interceptación SSE determinista y crear los flujos e2e en `apps/web/e2e/`: (a) listado `/projects` con estados y borrado, (b) crear proyecto en `/projects/new` (URL y subida con progreso + preview de preset), (c) `/projects/[id]` recibiendo eventos SSE hasta cards listas, editar metadatos, ajustar mini timeline y lanzar re-render, y multiselección con botón `"Publicar"` deshabilitado. Verificar ejecutando `pnpm --filter web test:e2e`.
- [x] 4.2 Actualizar `.github/workflows/ci.yml` para ejecutar `pnpm --filter web test` y `pnpm --filter web test:e2e` (con Chromium en headless), y documentar `pnpm gen:api` y los comandos de test web en `README.md`. Verificar que el YAML de CI es válido y los scripts documentados funcionan en local.

## 5. Verificación integrada

- [x] 5.1 Ejecutar `pnpm gen:api`, `pnpm --filter web lint`, `pnpm --filter web build`, `pnpm --filter web test`, `pnpm --filter web test:e2e`, comprobar responsive (móvil y escritorio) en desarrollo local con `pnpm dev`, y ejecutar `openspec validate add-web-ui-cards --strict` sin errores.

## Workflow follow-up

- Revisión del orquestador y merge de la rama `change/add-web-ui-cards` en `main`.
- Archivar el change con `openspec archive add-web-ui-cards` una vez aprobado.
