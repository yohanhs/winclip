# Proposal

## Why

Una vez disponible la API REST y la cola asíncrona del change `add-api-jobs`, el usuario necesita una interfaz web moderna y rápida para crear proyectos desde URL o archivo local, seguir el progreso de cada etapa en tiempo real y revisar, editar, recortar, re-renderizar o descargar los shorts generados como cards 9:16 sin recurrir a la línea de comandos.

## What Changes

- Generación del cliente TypeScript tipado en `packages/api-client` a partir del esquema OpenAPI de la API (`openapi-typescript` + `openapi-fetch`) mediante el script raíz `pnpm gen:api`, sin usar `any`.
- Página `/projects`: listado de proyectos con estado, miniatura, número de clips, progreso en vivo conectado al stream SSE, acceso directo a creación/detalle, eliminación con confirmación y estados vacíos, cargando y de error.
- Página `/projects/new`: formulario de creación con pestañas `URL | Subir archivo` (zona drag & drop y barra de progreso real de subida), selector de cantidad de clips (slider + opción `"Máximo posible"`), selector de idioma (`auto`, `es`, `en`), selector de campaña visible pero deshabilitado hasta el change 6, selector de preset de subtítulos con previsualización visual en vivo y selector de modo de reframe.
- Página `/projects/[id]`: barra de progreso por etapas (`Descarga`, `Transcripción`, `Selección`, `Render`) actualizada en tiempo real por SSE con cancelación del trabajo activo, y grid responsive de cards 9:16 con vista previa (`hover-play` silenciado y reproducción interactiva), score, título, hook, duración y hashtags.
- Acciones de revisión sobre cada clip: editar metadatos (`title`, `description`, `hashtags`), ajustar inicio/fin con mini timeline y lanzar re-renderizado, descargar el MP4, eliminar con confirmación y barra de multiselección con botón `"Publicar"` deshabilitado hasta el change 8.
- Diseño oscuro moderno con `shadcn/ui`, responsive, toasts de retroalimentación, estados vacíos/cargando/error consistentes y suite de tests de componentes (Vitest + Testing Library) más tests e2e con Playwright y API mockeada (MSW).

**Fuera de alcance:** gestión y creación de campañas (`add-campaign-rules`), conexión de cuentas sociales OAuth/Playwright (`add-social-accounts`), flujo real de publicación o programación (`add-publishers`), editor multipista de video avanzado, y autenticación de usuarios.

## Capabilities

### New Capabilities
- `web-dashboard`: cliente API tipado generado desde OpenAPI, experiencia visual oscura y responsive, listado en vivo de proyectos (`/projects`) y formulario de creación con subida en progreso y preview de presets (`/projects/new`).
- `clip-review`: vista de detalle de proyecto (`/projects/[id]`) con seguimiento en vivo por etapas SSE, grid de cards 9:16 con preview hover-play, edición de metadatos, ajuste de tiempos con mini timeline y re-render, descarga, eliminación y multiselección preparada para publicación.

### Modified Capabilities

## Impact

- Código nuevo y modificado: `packages/api-client/` (`package.json`, script de generación, `src/schema.d.ts`, `src/client.ts`), `apps/web/app/projects/**`, `apps/web/components/**`, `apps/web/hooks/**`, `apps/web/lib/**`, `apps/web/tests/**` (Vitest + Playwright + handlers MSW), `package.json` raíz (`pnpm gen:api`), `.github/workflows/ci.yml` (ejecución de tests web), `README.md`.
- Nuevas dependencias JS/TS: `openapi-typescript`, `openapi-fetch`, `sonner` (toasts de shadcn/ui), `vitest`, `@vitejs/plugin-react`, `jsdom`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`, `msw`, `@playwright/test`.
