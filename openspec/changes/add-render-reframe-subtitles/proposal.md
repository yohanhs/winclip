# Proposal

## Why

Tras ingerir, transcribir con marcas por palabra y seleccionar los mejores fragmentos de un video largo, WinClip necesita producir los clips verticales 9:16 listos para publicar en Shorts, Reels y TikTok. Sin una etapa de render automatizado que reencuadre al hablante, queme subtítulos karaoke legibles y entregue vídeo, miniatura y metadatos reproducibles desde la CLI, el usuario seguiría editando y subtitulando cada clip manualmente.

## What Changes

- Comando CLI `winclip render <project_id> [--clip <candidate_id>|--all] [--preset <nombre>] [--reframe face|center|blur] [--engine ass|pil]` (con opciones de recorte manual, hook, marca de agua, fuente y `--force`) que renderiza uno o todos los candidatos seleccionados en `storage/projects/<project_id>/clips/<clip_id>/`.
- Reencuadre vertical 9:16 (`1080x1920`) con tres modos: seguimiento facial suavizado con detección de cambios de plano y respaldo automático al centro (`face`), recorte estático con ajustes manuales de posición y zoom (`center`), y encuadre completo sobre fondo desenfocado (`blur`), respetando sin recortar las fuentes que ya son verticales.
- Motor de subtítulos palabra-a-palabra (karaoke) con dos motores seleccionables: motor por defecto basado en subtítulos vectoriales `.ass` y motor alternativo basado en renderizado de fotogramas rasterizados (portado del flujo previo del usuario), posicionados en zona segura por encima de la interfaz de Shorts/Reels/TikTok y con punto de extensión preparado para emojis.
- Cuatro presets de subtítulos en `assets/subtitle-presets/` (`bold-yellow`, `hormozi`, `clean-white`, `mrbeast`) usando fuentes OFL del repositorio (añadiendo `Noto Color Emoji` con su licencia OFL) y soporte local opcional de fuentes comerciales en `USER_FONTS_DIR`.
- Renderizado de clip en una sola pasada cuando sea posible: salida H.264 acelerada por hardware en Apple Silicon (`1080x1920`, hasta `30 fps`), audio AAC 192 kbps normalizado a `-14 LUFS`, overlay opcional del hook en los primeros segundos, marca de agua opcional, miniatura `thumb.jpg` con selección de fotograma con rostro, manifiesto `render.json` exacto al contrato `docs/architecture.md §6.3`, idempotencia por parámetros y callback de progreso.

**Fuera de alcance:** endpoints HTTP, cola de jobs en SQLite y worker en segundo plano (`add-api-jobs`), interfaz web de previsualización o edición de subtítulos (`add-web-ui-cards`), reglas automáticas de campaña (`add-campaign-rules`), publicación en redes (`add-publishers`), generación automática de emojis mediante LLM o diccionarios, pistas de música de fondo y B-roll.

## Capabilities

### New Capabilities
- `vertical-reframe`: transformación de video horizontal o vertical a encuadre 9:16 mediante seguimiento facial suavizado con detección de cortes, recorte manual con zoom, fondo desenfocado o paso directo cuando la fuente ya es vertical.
- `subtitle-rendering`: re-temporización de palabras transcritas, agrupación en líneas karaoke, aplicación de presets configurables, resolución segura de fuentes OFL/locales y renderizado mediante motor `ass` o `pil`.
- `clip-render`: orquestación del renderizado completo de candidatos por CLI y API interna del pipeline, generando `clip.mp4`, `thumb.jpg`, `subs.ass` y `render.json` con normalización de audio, overlay de hook, marca de agua, idempotencia y reporte de progreso.

### Modified Capabilities

## Impact

- Código nuevo en `apps/api/winclip/pipeline/`: `reframe.py`, `subtitles/` (`models.py`, `layout.py`, `fonts.py`, `ass_engine.py`, `pil_engine.py`, `presets.py`), `render.py`, `render_models.py`, más subcomando `render` en `apps/api/winclip/cli.py`.
- Assets nuevos en el repositorio: `assets/subtitle-presets/{bold-yellow,hormozi,clean-white,mrbeast}.json` y `assets/fonts/NotoColorEmoji/` con su `OFL.txt`.
- Tests nuevos en `apps/api/tests/`: tests unitarios con fotogramas sintéticos, tests de `.ass` contra archivos golden y test de integración `@pytest.mark.slow` con video sintético + medición de rendimiento en M1.
- Dependencias Python nuevas en `apps/api/pyproject.toml`: `opencv-python-headless`, `pillow`, `numpy`.
- Documentación actualizada en `README.md` con ejemplos de uso de `winclip render` y presets disponibles.
