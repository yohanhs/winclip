# Design

## Context

`setup-foundation` dejó `apps/web` (Next.js 15 App Router, TypeScript strict, Tailwind v4, shadcn/ui, TanStack Query) con el layout base, sidebar y `packages/api-client` vacío. `add-api-jobs` entrega la API REST bajo `/api`, el stream SSE en `/api/events` y un esquema OpenAPI con `operationId` estables. Véase `proposal.md` para la motivación y el alcance.

## Goals / Non-Goals

**Goals:**
- Generar un cliente TypeScript 100 % tipado en `packages/api-client` con `pnpm gen:api` y cero `any` en toda la capa web.
- Construir un flujo fluido de creación (`/projects/new`), monitoreo (`/projects`) y revisión/edición de shorts 9:16 (`/projects/[id]`) sincronizado en tiempo real con SSE y caché de TanStack Query.
- Establecer una estrategia sólida de testing frontend (Vitest + Testing Library para componentes/hooks y Playwright + MSW para e2e sin depender de backend real en CI).

**Non-Goals:**
- Pantallas de campañas (`/campaigns`), cuentas sociales (`/accounts`) ni modal/flujo de publicación (changes 6, 7 y 8; en este change se dejan los puntos de enganche visibles y deshabilitados con tooltip claro).
- Autenticación, gestión de sesión o modo claro completo (el tema oscuro moderno es el modo principal).

## Contratos

Contratos nuevos introducidos por este change (alineados con `docs/architecture.md` y los contratos de `add-api-jobs`):

### 1. Paquete `packages/api-client` y comando `pnpm gen:api`
- Script raíz `"gen:api": "pnpm --filter @winclip/api-client gen"`.
- Flujo de generación: exporta el esquema OpenAPI directamente desde el paquete Python (`uv run --project apps/api python -c "import json; from winclip.main import app; print(json.dumps(app.openapi()))" > packages/api-client/openapi.snapshot.json`, o configurable vía `OPENAPI_SOURCE=http://localhost:8000/openapi.json`) y ejecuta `openapi-typescript` → `packages/api-client/src/schema.d.ts`. Así `pnpm gen:api` funciona incluso sin levantar el servidor HTTP.
- Exportaciones de `@winclip/api-client`:
  - `createApiClient(baseUrl: string)`: instancia de `openapi-fetch` tipada con `paths`.
  - Alias de tipos generados (`ProjectSummary`, `ProjectDetail`, `Clip`, `Job`, `SubtitlePreset`, `CreateProjectResponse`, `SseEvent`).
  - `uploadProjectWithProgress(baseUrl, formData, onProgress, signal)`: helper tipado sobre `XMLHttpRequest` que reporta progreso real `0..100` en subidas multipart grandes (limitación de `fetch` estándar en navegadores) y valida/tipa la respuesta contra `CreateProjectResponse`.

### 2. Rutas de `apps/web`
- `/projects`: dashboard con lista/grid de proyectos, botón "Nuevo proyecto", suscripción SSE global (`GET /api/events`) para refrescar progreso/estado en vivo.
- `/projects/new`: formulario en tarjeta centrada con pestañas `URL` | `Subir archivo`, controles de parámetros y componente `subtitle-preset-preview` en vivo.
- `/projects/[id]`: cabecera con título/estado/acciones, componente `pipeline-stepper` (4 etapas: `ingest` → Descarga, `transcribe` → Transcripción, `select` → Selección, `render` → Render), grid responsive `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4` de `clip-card` 9:16, drawers/dialogs `clip-edit-dialog` y `clip-trim-dialog` (mini timeline), y barra flotante `selection-action-bar`.

### 3. Sincronización SSE + TanStack Query
- Hook `use-project-events(projectId?)` abre un `EventSource` a `${NEXT_PUBLIC_API_URL}/api/events` (con `?project_id=...` en detalle).
- Mapeo de eventos a caché TanStack Query (`queryClient.setQueryData` / `invalidateQueries`):
  - `job.progress` → actualiza `progress`, `stage` y `status` en `["projects"]` y `["project", projectId]`.
  - `clip.ready` → invalida `["project-clips", projectId]` (con cache-busting `?v=<updated_at>` en `video_url`/`thumb_url` para reflejar re-renders) y muestra toast discreto.
  - `job.done` → invalida proyecto y clips, muestra toast de éxito.
  - `job.failed` → actualiza estado de fallo y muestra toast de error.
- Reconexión automática con backoff simple y resincronización de queries en `onopen` tras caída temporal.

### 4. Estructura de componentes en `apps/web` (kebab-case)
- `components/projects/`: `project-list.tsx`, `project-card.tsx`, `project-create-form.tsx`, `file-dropzone.tsx`, `subtitle-preset-preview.tsx`.
- `components/clips/`: `pipeline-stepper.tsx`, `clip-grid.tsx`, `clip-card.tsx`, `clip-player-dialog.tsx`, `clip-edit-dialog.tsx`, `clip-trim-dialog.tsx`, `mini-timeline.tsx`, `selection-action-bar.tsx`.
- `hooks/`: `use-api-client.ts`, `use-projects.ts`, `use-clips.ts`, `use-project-events.ts`.

## Decisions

1. **`openapi-typescript` + `openapi-fetch` con exportación offline del OpenAPI.**
   - *Por qué:* es el stack definido en `docs/architecture.md §3`, genera tipos puros con sobrecarga casi cero en runtime y evita `any`. Exportar `app.openapi()` vía `uv run` permite regenerar y verificar frescura en CI sin levantar procesos de red.
   - *Alternativa descartada:* `openapi-generator-cli` (requiere Java y genera clases verbosas) o escribir interfaces TS a mano (se desincronizan de la API).
   - *Dependencias nuevas:* `openapi-typescript` (devDep) y `openapi-fetch` (dep) en `packages/api-client`.

2. **Subida de archivo con progreso real mediante `XMLHttpRequest` encapsulado y tipado.**
   - *Por qué:* la API `fetch` en navegadores todavía no expone eventos de progreso de subida (`upload.onprogress`) de forma portable. Un pequeño wrapper `uploadProjectWithProgress` con soporte de `AbortSignal` y tipos derivados de `schema.d.ts` da progreso fluido en archivos de varios GB sin perder tipado estricto.
   - *Alternativa descartada:* `axios` (dependencia adicional innecesaria solo para upload progress) o barra indeterminada (mala UX en archivos grandes).

3. **Preview `hover-play` eficiente en cards 9:16.**
   - *Por qué:* montar decenas de `<video preload="auto">` simultáneos degrada la memoria del navegador. Cada `clip-card` renderiza la miniatura `<img>` (`loading="lazy"`) en reposo y monta o activa `<video muted loop playsInline preload="none">` al entrar el puntero (`onMouseEnter` / `onFocus`), llamando `play()` con captura silenciosa de `AbortError` y pausando/reseteando en `onMouseLeave`. En pantallas táctiles o al pulsar el botón de reproducir se abre `clip-player-dialog` con audio y controles nativos (usando Range requests de la API).
   - *Alternativa descartada:* autoplay permanente en todas las cards (alto consumo de CPU/ancho de banda).

4. **Mini timeline accesible y ligera para recorte `start`/`end`.**
   - *Por qué:* en lugar de importar una librería pesada de edición de video/ondas, `mini-timeline.tsx` implementa una barra de doble asa (sobre el slider de rango de Radix/shadcn + inputs de timecode `MM:SS.s` sincronizados y previsualización del fotograma/rango en el `<video>` del clip o del tiempo seleccionado). Cumple validación `0 <= start < end <= project.duration` y es trivial de testear con teclado y puntero.
   - *Alternativa descartada:* `wavesurfer.js` o editores canvas complejos (sobreingeniería para ajustar inicio/fin de un short y requieren servir el audio completo del video largo).

5. **Tema oscuro moderno con `shadcn/ui` y `sonner` para toasts.**
   - *Por qué:* `shadcn/ui` ya forma parte del stack; fijar `class="dark"` en el layout raíz con tokens de contraste elevado (fondo carbón/zinc, cards con borde sutil, acento amarillo/ámbar coherente con el highlight karaoke) ofrece una estética editorial limpia para video. `sonner` es el componente oficial recomendado por shadcn/ui para toasts modernos y accesibles.
   - *Alternativa descartada:* toast legacy de Radix (más código boilerplate y en desuso en shadcn/ui).
   - *Dependencia nueva:* `sonner` (y `lucide-react` si aún no estuviera añadida por shadcn/ui en el change 0).

6. **Estrategia de pruebas: Vitest + Testing Library + Playwright + MSW.**
   - *Por qué:* Vitest ofrece ejecución rápida en TypeScript/ESM junto a React Testing Library para lógica de formularios, `mini-timeline`, `subtitle-preset-preview` y `clip-card`; Playwright valida flujos completos en navegador real (creación URL/archivo, recepción SSE simulada, edición, trim/rerender, multiselección) interceptando la API con MSW (o `page.route` respaldado por los mismos fixtures MSW para SSE) de forma determinista y sin necesitar FFmpeg ni MLX en CI.
   - *Alternativa descartada:* Jest (configuración más pesada con ESM/Next 15) o e2e contra backend real en cada PR (lento y dependiente de modelos GPU).
   - *Dependencias nuevas (devDependencies en `apps/web`):* `vitest`, `@vitejs/plugin-react`, `jsdom`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`, `msw`, `@playwright/test`.

## Risks / Trade-offs

- [Re-render genera un nuevo `clip.mp4` en la misma URL `/api/clips/{id}/file` y el navegador sirve caché vieja] → Añadir query string de versión (`?v=<updated_at>` o contador de render) en `video_url`/`thumb_url` al recibir `clip.ready`.
- [SSE en Playwright con MSW puede requerir streaming `ReadableStream` en navegador] → Construir un helper de mock SSE reutilizable en los tests e2e (`Response` con `text/event-stream` y `ReadableStream` controlado desde el test) que permita emitir `job.progress`, `clip.ready` y `job.done` de forma determinista.
- [Diferencias en campos de `assets/subtitle-presets/*.json` definidos en el change 3] → Tipar el contrato de `GET /api/presets` con valores por defecto seguros en `subtitle-preset-preview.tsx` (fuente, color base, color activo, borde y posición) para degradar con gracia si un preset añade campos nuevos.
- [Subida de archivo cancelada o pestaña cerrada a mitad] → Enlazar `AbortController` al botón "Cancelar subida" y desmontaje del componente para abortar el `XMLHttpRequest` limpiamente.
