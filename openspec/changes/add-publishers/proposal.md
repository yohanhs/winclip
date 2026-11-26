# Proposal

## Why

Generar shorts renderizados con subtítulos y reglas de campaña solo resuelve la primera mitad del trabajo: el usuario todavía tiene que subir manualmente cada video a múltiples cuentas de YouTube, TikTok e Instagram, adaptar títulos/descripciones/hashtags por red, configurar fechas de programación y llevar control de qué se publicó dónde. Este change cierra el ciclo completo de WinClip con publicación y programación multi-cuenta directa desde la aplicación local.

## What Changes

- Interfaz unificada `Publisher` (`docs/architecture.md §8`) con implementaciones por plataforma y método:
  - `youtube_api` (YouTube Data API v3 para Shorts: título `<= 100` caracteres, descripción, tags, categoría, idioma, privacidad, programación nativa vía `publishAt`, miniatura, comentario fijado y control/aviso de cuota diaria de 10 000 unidades).
  - `tiktok_api` (TikTok Content Posting API v2: publicación directa cuando la cuenta tiene `video.publish` aprobado o envío a borradores inbox con aviso explícito cuando solo tiene `video.upload`, con polling de estado).
  - `instagram_graph` (Instagram Graph API para Reels usando subida reanudable directa del binario local vía `rupload.facebook.com`, evitando exponer WinClip a internet o depender de un bucket público).
  - Publicadores `playwright` para TikTok e Instagram como respaldo para cuentas de navegador (selectores aislados, capturas por paso y ante errores, pausas humanas, modo visible y detención inmediata ante desafíos anti-bot/2FA).
- Tipo de job `publish` integrado en la cola SQLite existente para publicar combinaciones `(clip × cuentas)`, con programación (nativa en YouTube; diferida por el worker en TikTok e Instagram), reintentos selectivos con backoff, idempotencia por `external_id`, límites diarios por cuenta, eventos SSE e historial en la tabla `publication`.
- Generación de metadatos por plataforma a partir del clip y la campaña asociada, con edición previa en un diálogo "Publicar" que permite multi-selección de clips y cuentas agrupadas por plataforma.
- Interfaz web en `/publications` con historial filtrable, estado en vivo, enlace externo al video publicado, detalle de error con visor de captura de pantalla, reintento y cancelación de publicaciones programadas.

**Fuera de alcance:** analíticas posteriores a la publicación (vistas, retención, likes), publicación en otras redes (X, LinkedIn, Facebook Reels), evasión de CAPTCHAs o uso de proxies residenciales, edición de video dentro del flujo de publicación y publicación distribuida multi-tenant.

## Capabilities

### New Capabilities
- `publishing`: publicación y programación multi-cuenta de clips en YouTube, TikTok e Instagram mediante APIs oficiales o navegador automatizado de respaldo, con metadatos editables, idempotencia, control de cuotas/límites, cola de jobs e historial web.

### Modified Capabilities

## Impact

- Backend (`apps/api`): módulos `winclip/publishers/{base,registry,metadata,youtube_api,tiktok_api,instagram_graph}.py` y `winclip/publishers/playwright/{selectors,tiktok,instagram}.py`, router `winclip/routers/publications.py`, tabla `publication` en `core/models.py`, nuevo handler `publish` y soporte de jobs diferidos (`run_at`) en `worker/{queue,handlers}.py`.
- Frontend (`apps/web`): diálogo "Publicar" integrado en `/projects/[id]` (multi-clip y multi-cuenta) y página `/publications` con visor de capturas, reintentos y cancelación.
- Cliente tipado (`packages/api-client`): regeneración desde OpenAPI con endpoints de publicaciones y previsualización de metadatos.
- Dependencias: reutiliza las dependencias ya introducidas en `add-social-accounts` (`google-api-python-client`, `playwright`) y `httpx` existente; no requiere librerías nuevas.
