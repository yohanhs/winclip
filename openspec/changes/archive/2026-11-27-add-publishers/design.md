# Design

## Context

Ver `proposal.md` para la motivación. Este change depende de `add-campaign-rules` (metadatos de campaña: CTA, hashtags, idioma, plataformas objetivo) y `add-social-accounts` (entidad `social_account`, credenciales OAuth cifradas con refresco automático y perfiles persistentes Playwright). La UI de `/publications` y el diálogo `PublishDialog` siguen `docs/ui-design.md`.

`docs/architecture.md` fija:
- Estructura de módulos (§3): `winclip/publishers/{base,youtube_api,tiktok_api,instagram_graph}.py`, `winclip/publishers/playwright/{session,tiktok,instagram}.py` y `winclip/routers/publications.py`.
- Interfaz `Publisher(Protocol)` (§8): `platform`, `check(account) -> AccountStatus`, `publish(clip, account, meta) -> PublishResult`.
- Modelo base `publication` (§7): `id, clip_id, account_id, status (scheduled|publishing|published|failed), scheduled_at, external_id, external_url, error, screenshot_path`.
- Trabajo previo verificado del autor: `subir.py` (YouTube Data API v3 con `MediaFileUpload`, `publishAt`, miniatura y comentario) y `subir_tiktok.py` (TikTok Content Posting API v2 `inbox/video/init` + `PUT`).

## Goals / Non-Goals

**Goals:**
- Implementar la interfaz `Publisher` de forma uniforme para 3 APIs oficiales y 2 respaldos por navegador, seleccionables dinámicamente según `(platform, auth_method)`.
- Resolver la publicación de Reels en Instagram Graph desde un archivo MP4 100% local sin túneles públicos ni almacenamiento en la nube.
- Garantizar idempotencia, límites diarios, programación clara y observabilidad (progreso SSE, capturas de error, historial persistente).
- Documentar y mitigar de forma explícita los riesgos de Términos de Servicio (ToS) al usar automatización por navegador.

**Non-Goals:**
- Evadir controles anti-bot, CAPTCHAs o verificaciones 2FA.
- Ejecutar programación remota en la nube para TikTok/Instagram cuando el Mac del usuario esté apagado (se documenta claramente que solo YouTube tiene programación nativa en servidor).
- Recolectar métricas post-publicación (views/likes/comentarios).

## Decisions

1. **Interfaz `Publisher` y registro por `(platform, auth_method)` (`winclip/publishers/base.py`, `registry.py`).**
   - `Publisher` sigue exactamente `docs/architecture.md §8` con DTOs Pydantic `PublishMeta`, `PublishResult(external_id, external_url, delivery_mode, warnings, screenshot_path)` y `AccountStatus`.
   - `get_publisher(account)` resuelve:
     - `("youtube", "api")` → `YouTubeApiPublisher`
     - `("tiktok", "api")` → `TikTokApiPublisher`
     - `("instagram", "api")` → `InstagramGraphPublisher`
     - `("tiktok", "playwright")` → `TikTokPlaywrightPublisher`
     - `("instagram", "playwright")` → `InstagramPlaywrightPublisher`
   - Antes de ejecutar `publish`, cada publicador API obtiene credenciales frescas mediante `get_valid_credentials(account)` de `add-social-accounts`.
   - *Alternativa descartada:* condicionales gigantes en el worker por plataforma. El `Protocol` + registro permite testear cada publicador de forma aislada y añadir nuevas redes sin tocar el worker.

2. **YouTube Shorts vía YouTube Data API v3 (`winclip/publishers/youtube_api.py`).**
   - Valida título (`1–100` chars), descripción (`<= 5000` chars, añadiendo CTA y hashtags), tags (`<= 500` chars totales), `categoryId` (default `"22"`), `defaultLanguage` y `privacyStatus`.
   - Subida reanudable con `MediaFileUpload(clip_path, mimetype="video/mp4", chunksize=8*1024*1024, resumable=True)` reportando porcentaje de avance (`10%–80%`) al job vía callback.
   - Si `meta.scheduled_at` está en el futuro: envía `status.privacyStatus = "private"` y `status.publishAt = scheduled_at.astimezone(UTC).isoformat().replace("+00:00", "Z")`.
   - Pasos secundarios no fatales (si ya existe `external_id`):
     - Miniatura (`thumbnails().set(videoId=..., media_body=thumb_path)`): si devuelve 403 (canal sin verificación telefónica para miniaturas personalizadas), añade advertencia en `warnings` sin marcar la publicación como fallida.
     - Comentario fijado (`commentThreads().insert(...)` si `meta.pinned_comment` no está vacío): publica el comentario superior con el token `youtube.force-ssl` y añade advertencia si el API no soporta fijado automático o si el canal tiene comentarios deshabilitados, sin tumbar la publicación.
   - Control de cuota diaria: cada `videos.insert` consume ~1 600 unidades de la cuota estándar de 10 000 unidades/día (~6 videos/día por proyecto Google). Se calcula el consumo estimado del día sobre publicaciones `youtube/api` y se expone un contador + aviso en `/api/publications/quota` y en el diálogo "Publicar". Si Google devuelve HTTP 403 `quotaExceeded`, se clasifica como error no reintentable (`QuotaExceededError`).

3. **TikTok vía Content Posting API v2 (`winclip/publishers/tiktok_api.py`).**
   - Inspecciona `account.capabilities_json["direct_post"]`:
     - Si es `true` (scope `video.publish` concedido y modo solicitado `direct`): llama a `POST https://open.tiktokapis.com/v2/post/publish/video/init/` con `source_info.source = "FILE_UPLOAD"`, `video_size`, `chunk_size` y `total_chunk_count`, más `post_info` (`title`, `privacy_level`, `disable_duet`, `disable_comment`, `disable_stitch`).
     - Si es `false` (solo `video.upload`, caso estándar sin auditoría aprobada): llama a `POST https://open.tiktokapis.com/v2/post/publish/inbox/video/init/` (`FILE_UPLOAD`) y devuelve `delivery_mode = "inbox"` con advertencia explícita para que el usuario complete el borrador en la app móvil de TikTok.
   - Sube el MP4 mediante `PUT` al `upload_url` con headers `Content-Range` y `Content-Type: video/mp4` (respetando chunking cuando `video_size` supera el tamaño mínimo de chunk de TikTok).
   - Hace polling a `POST https://open.tiktokapis.com/v2/post/publish/status/fetch/` con `publish_id` (backoff progresivo hasta 3 min) hasta `PUBLISH_COMPLETE`, `SEND_TO_USER_INBOX` o `FAILED`.
   - Usa `httpx` directamente (sin SDK no oficial).

4. **Instagram Reels vía Instagram Graph API con subida reanudable local (`winclip/publishers/instagram_graph.py`).**
   - **Problema:** el flujo clásico de `POST /{ig-user-id}/media` con `video_url` exige una URL HTTPS públicamente accesible por los servidores de Meta, incompatible con una app 100% local.
   - **Solución elegida — Resumable Upload (`rupload.facebook.com`):**
     1. Crear contenedor de Reel: `POST https://graph.facebook.com/v21.0/{ig_user_id}/media` con `media_type=REELS`, `upload_type=resumable`, `caption=...`, `share_to_feed=true|false`, `thumb_offset` opcional. Meta devuelve `{id: container_id, uri: "https://rupload.facebook.com/ig-api-upload/v21.0/<container_id>"}`.
     2. Subir binario local directamente: `POST <uri>` con headers `Authorization: OAuth <access_token>`, `offset: 0`, `file_size: <bytes>` y el stream del archivo MP4 local (con soporte de consulta de offset si hay corte de red).
     3. Polling de estado: `GET https://graph.facebook.com/v21.0/{container_id}?fields=status_code,status` hasta `FINISHED` (o error `ERROR`/`EXPIRED`).
     4. Publicar contenedor: `POST https://graph.facebook.com/v21.0/{ig_user_id}/media_publish?creation_id={container_id}`, y obtener `permalink` con `GET /{media_id}?fields=permalink`.
   - **Alternativas descartadas:**
     - *Túnel efímero (ngrok / cloudflared):* añade dependencia externa, superficie de ataque al exponer la API local a internet y falla en redes restringidas.
     - *Bucket S3/R2 temporal:* rompe el requisito local-first y obliga al usuario a configurar y pagar almacenamiento en la nube antes de publicar. (En el futuro SaaS, `Storage` Protocol permitirá alternar a URL firmada si se desea).

5. **Publicadores Playwright de respaldo (`winclip/publishers/playwright/{selectors,tiktok,instagram}.py`).**
   - Solo se invocan para cuentas con `auth_method == "playwright"`.
   - **Aislamiento de selectores:** todos los selectores CSS/ARIA/texto viven en `selectors.py` con listas ordenadas de fallbacks por paso (botón subir, input `type="file"`, campo caption, botón publicar, indicador de publicación completada, indicadores de login/CAPTCHA), desacoplando los flujos del DOM volátil.
   - **Flujo humano y trazable:**
     - Lanza el perfil persistente `storage/accounts/<account_id>/profile` en modo visible (`headless=False`, configurable por `PLAYWRIGHT_HEADLESS=false` default) adquiriendo un lock por `account_id` para evitar dos navegadores simultáneos sobre el mismo perfil.
     - Inserta delays aleatorios entre interacciones (0.8–2.5 s) y escritura escalonada en campos de texto.
     - Guarda capturas PNG por paso clave en `storage/publications/<publication_id>/steps/<step>.png` y guarda la última/fallida en `publication.screenshot_path` (expuesta vía `GET /api/publications/{id}/screenshot`).
     - **Parada segura ante retos:** antes y después de pasos críticos comprueba señales de redirección a login, verificación 2FA o desafíos CAPTCHA/anti-bot. Si detecta cualquiera, **aborta inmediatamente** (sin intentar resolver ni eludir), captura pantalla, clasifica el error como `ChallengeDetectedError` / `AuthExpiredError` (no reintentable) y actualiza el estado para intervención manual.

6. **Cola de jobs `publish`, programación, reintentos, idempotencia y límites diarios.**
   - Se añade el campo opcional `run_at (datetime UTC nullable)` a la tabla `job` (compatible hacia atrás con `NULL = ejecutar inmediatamente`) y el handler `publish` en `worker/handlers.py`.
   - Los jobs `publish` se ejecutan fuera del semáforo exclusivo de GPU (pueden correr mientras MLX/FFmpeg no bloqueen o en concurrencia controlada por red), manteniendo exclusión mutua por `account_id` para cuentas Playwright.
   - **Programación:**
     - YouTube API con `scheduled_at` futuro: el job se encola con `run_at = NULL` para subir de inmediato a YouTube con `publishAt` nativo; al completar la subida, `publication.status = "scheduled"` y guarda `external_id`/`external_url`.
     - TikTok e Instagram (API y Playwright) con `scheduled_at` futuro: `publication.status = "scheduled"` y `job.run_at = scheduled_at`. El worker selecciona solo jobs donde `run_at IS NULL OR run_at <= now()`. La UI muestra explícitamente el aviso "Requiere que WinClip y el worker estén activos a la hora programada" para TikTok/Instagram.
     - Cancelación (`POST /api/publications/{id}/cancel`): en TikTok/Instagram cancela el job pendiente y pasa la publicación a `cancelled`. En YouTube ya subido con `publishAt`, marca `cancelled` localmente e informa claramente (con opción de llamar `videos().delete` solo si el usuario lo confirma explícitamente).
   - **Idempotencia:**
     - Al crear publicaciones, si ya existe una publicación activa (`scheduled`, `publishing`) o `published` para `(clip_id, account_id)`, la API rechaza con 409 salvo `force=true`.
     - Al reintentar una `publication` fallida que ya registró `external_id` (p. ej. el video se subió pero falló la miniatura o el paso final de guardado), el publicador salta la resubida del archivo y solo completa pasos pendientes o consulta el estado remoto del `external_id`.
   - **Reintentos:** backoff exponencial (p. ej. 30 s, 2 min, 10 min; máx. 3 intentos) solo para errores clasificados como `TransientPublishError` (red, timeouts, HTTP 5xx, 429 temporal). Errores permanentes (`AuthExpiredError`, `QuotaExceededError`, `ValidationError`, `ChallengeDetectedError`) fallan en el primer intento sin reintentos ciegos.
   - **Límites diarios por cuenta:** por defecto conservadores (`youtube/api: 6`, `tiktok/api: 10`, `instagram/api: 25`, `playwright: 5`), ajustables por cuenta/configuración. Se validan antes de encolar y antes de publicar en el worker.

7. **Generación de metadatos (`winclip/publishers/metadata.py`) y diálogo "Publicar".**
   - Función pura `build_platform_meta(clip, campaign, platform)` que construye defaults listos para editar:
     - YouTube: `title` (recortado limpiamente a `<= 100` chars), `description` (descripción del clip + `cta_text` de campaña + hashtags fusionados + `#Shorts`), `tags` (derivados de hashtags sin `#`), `category_id="22"`, `language`, `privacy="public"`, `pinned_comment` opcional (pre-rellenado con `cta_text` si existe).
     - TikTok: `caption` (título/descripción + `cta_text` + hashtags, máx. 2 200 chars), `privacy_level="PUBLIC_TO_EVERYONE"`, toggles de comentarios/duet/stitch.
     - Instagram: `caption` (descripción + `cta_text` + hashtags, máx. 2 200 chars), `share_to_feed=True`.
   - En `/projects/[id]`, el diálogo "Publicar" admite seleccionar 1 o N clips renderizados y M cuentas conectadas agrupadas por plataforma (preseleccionando cuentas por defecto de `campaign.target_platforms`), con edición de metadatos por plataforma/clip, contadores de caracteres, avisos de cuota/inbox/Playwright y selector de fecha/hora programada.

8. **Dependencias nuevas.**
   - No se requieren nuevas dependencias externas: se reutilizan `google-api-python-client`, `google-auth`, `playwright` (añadidos en `add-social-accounts`) y `httpx` (presente desde `setup-foundation`).

## Contratos

Extensiones compatibles sobre `docs/architecture.md §5`, `§7` y `§8`:

- **Tabla `publication` (extensión compatible con §7):**
  `id (ULID), workspace_id, clip_id, account_id, job_id (nullable), status (scheduled|publishing|published|failed|cancelled), delivery_mode (direct|inbox), scheduled_at (nullable), published_at (nullable), meta_json (TEXT/JSON), external_id (nullable), external_url (nullable), error (nullable), error_code (nullable), warnings_json (TEXT/JSON), screenshot_path (nullable), attempts (int), created_at, updated_at`.
- **Tabla `job` (extensión compatible con §7):**
  se añade `run_at (datetime UTC nullable)` para jobs diferidos y nuevo `type = "publish"`.
- **Almacenamiento local de capturas:**
  `storage/publications/<publication_id>/steps/<nn>_<step>.png` (gitignored bajo `STORAGE_DIR`).
- **Endpoints `/api/publications`:**
  - `POST /api/publications/preview-meta` → recibe `{clip_ids, account_ids}` → devuelve metadatos propuestos por `(clip_id, account_id)` más avisos de cuota, límite diario, modo inbox y modo Playwright.
  - `POST /api/publications` → recibe `{items: [{clip_id, account_id, meta, scheduled_at?}], force?: bool}` → crea publicaciones + jobs `publish` → `201`.
  - `GET /api/publications` → lista filtrable por `project_id`, `clip_id`, `account_id`, `platform`, `status`, ordenada por `created_at DESC`.
  - `GET /api/publications/{id}` → detalle completo (incluyendo `warnings`, `steps_screenshots`).
  - `GET /api/publications/{id}/screenshot` → sirve la imagen PNG de `screenshot_path` (validando ruta dentro de `STORAGE_DIR`).
  - `POST /api/publications/{id}/retry` → reencola una publicación `failed` respetando idempotencia por `external_id`.
  - `POST /api/publications/{id}/cancel` → cancela una publicación `scheduled` (y su job diferido pendiente).
  - `GET /api/publications/quota` → resumen de uso diario y límites por cuenta conectada.

## Risks / Trade-offs

- **[Riesgo ToS de automatización por navegador en TikTok e Instagram]** → Los Términos de Servicio de TikTok e Instagram restringen la automatización de sus interfaces web; su uso conlleva riesgo de retos anti-bot frecuentes, reducción de alcance (shadowban), bloqueos temporales o suspensión de cuenta. **Mitigaciones:** (1) priorizar siempre las APIs oficiales (`youtube_api`, `tiktok_api`, `instagram_graph`) y mostrar aviso explícito de riesgo ToS al conectar o publicar con cuentas Playwright; (2) modo visible con pausas humanas y perfiles aislados por cuenta; (3) límite diario conservador (default 5/día); (4) parada inmediata ante CAPTCHA/2FA sin ningún intento de evasión ni reintento automático.
- **[Cambios frecuentes en el DOM web de TikTok e Instagram rompen Playwright]** → Selectores centralizados y aislados en `winclip/publishers/playwright/selectors.py` con fallbacks, capturas automáticas por paso para diagnóstico rápido y tests de flujo contra páginas HTML fixture.
- **[Cuota diaria de YouTube Data API v3 muy ajustada (10 000 unidades = ~6 subidas/día)]** → Contador visible de consumo diario en API y UI, aviso preventivo antes de confirmar el lote y detección de `quotaExceeded` sin quemar reintentos.
- **[TikTok API sin auditoría aprobada solo entrega a Inbox]** → Detección automática vía `capabilities_json`, fallback limpio a `inbox/video/init` con `delivery_mode="inbox"` y badge/aviso claro en `/publications` y en el diálogo "Publicar".
- **[WinClip apagado a la hora programada de TikTok o Instagram]** → El worker recupera jobs con `run_at <= now()` al reiniciarse (con ventana configurable para no publicar sorpresivamente días tarde sin confirmación, marcando como `failed` con motivo `missed_schedule_window` si supera p. ej. 2 horas) y la UI advierte previamente que YouTube programa en servidor mientras TikTok/Instagram requieren el worker local encendido.
- **[Subida de Instagram Graph falla por códec/relación de aspecto incompatible]** → Validación previa de requisitos de Reels (MP4 H.264/AAC, 9:16, duración dentro de límites de Meta) antes de iniciar la transferencia a `rupload.facebook.com`.
