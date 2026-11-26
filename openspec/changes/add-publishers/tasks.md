# Tasks

## 1. Contratos, metadatos, modelo de datos y cola de publicación

- [ ] 1.1 Implementar `winclip/publishers/base.py` (interfaz `Publisher` de `docs/architecture.md §8`, `PublishMeta`, `PublishResult`, `AccountStatus`, jerarquía de errores transitorios vs permanentes) y `winclip/publishers/registry.py`. Verificar con `uv run --project apps/api pytest tests/test_publisher_base.py`.
- [ ] 1.2 Implementar `winclip/publishers/metadata.py` con la generación y validación de metadatos por plataforma (`youtube`, `tiktok`, `instagram`) a partir de `clip + campaign` (límite de 100 caracteres en título de YouTube, fusión de CTA y hashtags, `#Shorts`, tags y captions). Verificar con `uv run --project apps/api pytest tests/test_publish_metadata.py`.
- [ ] 1.3 Añadir el modelo SQLModel `Publication` en `winclip/core/models.py` (con `status`, `delivery_mode`, `scheduled_at`, `external_id`, `external_url`, `error`, `error_code`, `warnings_json`, `screenshot_path`, `meta_json`, `attempts`), añadir `run_at` a `Job` y actualizar `worker/queue.py` para respetar `run_at <= now()` y cancelación de jobs programados. Verificar con `uv run --project apps/api pytest tests/test_publish_queue.py`.

## 2. Publicadores oficiales por API

- [ ] 2.1 Implementar `winclip/publishers/youtube_api.py` (Shorts: `MediaFileUpload` reanudable con progreso, título `<= 100`, descripción, tags, categoría, idioma, privacidad, programación nativa con `privacyStatus="private"` + `publishAt`, miniatura y comentario fijado como pasos secundarios no fatales, control de cuota diaria 10k unidades e idempotencia por `external_id`). Verificar con `uv run --project apps/api pytest tests/test_publisher_youtube.py` usando mocks de la API de Google para subida inmediata, programada, cuota agotada, fallo de miniatura e idempotencia.
- [ ] 2.2 Implementar `winclip/publishers/tiktok_api.py` (Content Posting API v2 con `httpx`: Direct Post cuando `capabilities.direct_post` es verdadero, fallback automático a `inbox/video/init` con `delivery_mode="inbox"` y aviso cuando solo existe `video.upload`, subida `PUT` en chunks y polling a `status/fetch`). Verificar con `uv run --project apps/api pytest tests/test_publisher_tiktok_api.py` cubriendo ambos modos y fallo remoto.
- [ ] 2.3 Implementar `winclip/publishers/instagram_graph.py` (Reels vía Instagram Graph API usando `upload_type=resumable` y subida binaria local directa a `rupload.facebook.com`, polling de `status_code` hasta `FINISHED`, `media_publish` y obtención de `permalink`, más validación previa de formato MP4/Reels). Verificar con `uv run --project apps/api pytest tests/test_publisher_instagram_graph.py` simulando el flujo resumable completo y errores de procesamiento.

## 3. Publicadores Playwright de respaldo

- [ ] 3.1 Crear `winclip/publishers/playwright/selectors.py` con selectores aislados y fallbacks por paso para TikTok e Instagram, además de utilidades comunes (delays humanos, lock por `account_id`, capturas por paso bajo `storage/publications/<id>/steps/`, detector de sesión expirada y de desafíos CAPTCHA/2FA con parada inmediata sin evasión). Verificar con `uv run --project apps/api pytest tests/test_playwright_common.py`.
- [ ] 3.2 Implementar `winclip/publishers/playwright/tiktok.py` e `instagram.py` en modo visible usando el perfil persistente de la cuenta, generando capturas por paso y ante fallo y abortando limpiamente ante cualquier desafío anti-bot/login. Verificar con tests contra páginas HTML fixture locales en `tests/test_playwright_publishers.py` comprobando guardado de capturas y detención ante reto.

## 4. Handler del worker, API REST de publicaciones y documentación

- [ ] 4.1 Implementar el handler `publish` en `winclip/worker/handlers.py` con refresco de credenciales, verificación de límites diarios por cuenta, reintentos con backoff solo para errores transitorios, ventana de programación perdida (`missed_schedule_window`), idempotencia por `external_id` y emisión de eventos SSE. Verificar con `uv run --project apps/api pytest tests/test_publish_worker.py`.
- [ ] 4.2 Implementar `winclip/routers/publications.py` (`POST /preview-meta`, `POST /`, `GET /`, `GET /{id}`, `GET /{id}/screenshot`, `POST /{id}/retry`, `POST /{id}/cancel`, `GET /quota`) con protección contra duplicados activos (409 sin `force=true`) y registrarlo en `winclip/main.py`. Verificar con `uv run --project apps/api pytest tests/test_publications_api.py`.
- [ ] 4.3 Documentar en `README.md` la publicación multi-cuenta, cuotas de YouTube (10k/día), modo inbox vs Direct Post en TikTok, subida local a Instagram Graph y advertencias ToS de Playwright; regenerar `packages/api-client`. Verificar que `packages/api-client` compila sin errores y refleja todos los endpoints nuevos.

## 5. Interfaz web: diálogo "Publicar" y página `/publications`

- [ ] 5.1 Implementar el diálogo "Publicar" en `apps/web` e integrarlo en `/projects/[id]` (desde una card individual y mediante multi-selección de clips renderizados): selección de cuentas agrupadas por plataforma (con preselección de cuentas por defecto), pestañas de metadatos editables por plataforma con contadores de caracteres, avisos de cuota/inbox/ToS Playwright y selector de publicación inmediata o programada. Verificar con `pnpm --filter web lint && pnpm --filter web build` y prueba manual contra la API local.
- [ ] 5.2 Implementar la página `/publications` en `apps/web`: listado filtrable por plataforma, cuenta, estado y proyecto, actualizaciones de estado en tiempo real vía SSE, enlace externo clickable, detalle de error con modal visor de captura de pantalla, botón "Reintentar" en fallidas y "Cancelar" en programadas. Verificar manualmente el ciclo completo (encolar, ver progreso SSE, inspeccionar error con captura, reintentar y cancelar programada).

## 6. Verificación integrada

- [ ] 6.1 Ejecutar `uv run --project apps/api ruff check . && uv run --project apps/api ruff format --check . && uv run --project apps/api pytest`, `pnpm --filter web lint && pnpm --filter web build`, verificar un flujo integrado en modo prueba (diálogo Publicar multi-cuenta → worker `publish` → seguimiento en `/publications`) y ejecutar `openspec validate add-publishers --strict` sin errores.

## Workflow follow-up

- Revisión del orquestador y del usuario (incluyendo validación opcional con una subida real privada/borrador tras confirmación explícita del usuario).
- Archivar el change con `openspec archive add-publishers` tras la aprobación.
