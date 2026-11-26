# WinClip: referencia oficial de diseño UI

Esta guía recoge el sistema visual aprobado por el usuario para la interfaz web de WinClip (`apps/web`, Next.js 16 + Tailwind v4 + shadcn/ui). Aplica a los changes `add-web-ui-cards` (5), `add-campaign-rules` (6), `add-social-accounts` (7) y `add-publishers` (8).

> **Prototipo de referencia (solo lectura, fuera del repo):** en la máquina del autor existe el prototipo interactivo aprobado en `/Volumes/yohan/Proyectos/winclip/winclip-—-estudio-local-de-clipping-ia/` (React + Tailwind v4). Puede consultarse como referencia visual y de estructura, pero el código productivo siempre se implementa en `apps/web` conectado al cliente tipado `packages/api-client` y a la API real (nunca copiar datos mock ni dependencias de Vite).

## 1. Sistema de diseño y tokens (`globals.css`)

- **Tema:** oscuro por defecto (estética desktop studio densa y sobria, sin gradientes púrpura genéricos).
- **Superficies:**
  - Lienzo principal: `#09090B`
  - Sidebar / encabezados de tabla: `#0D0D10`
  - Tarjetas y modales: `#111114` (elevado `#141418` / `#18181B`)
  - Bordes: `1px solid rgba(255, 255, 255, 0.08)` (hover `0.16–0.18`, foco `amber-400/60`)
- **Acentos y semántica:**
  - Primario (CTA y resaltado activo): ámbar/dorado `#F59E0B` (`bg-amber-400 hover:bg-amber-300 text-zinc-950`) y amarillo karaoke `#FFD600`.
  - Éxito / listo / score ≥ 90 / conectado: esmeralda `#10B981` (`emerald-400`).
  - Procesando / etapas IA: cian (`cyan-400`) y violeta (`violet-400`, también para badges de campos inferidos por IA y Playwright).
  - Peligro / expirada / error: rosa/rojo (`rose-400`, borde `rose-500/35`).
- **Tipografía:**
  - UI: `Plus Jakarta Sans` (con `Inter` como alternativa/fallback OFL).
  - Timestamps, métricas, badges de idioma, scores, handles y JSON: `JetBrains Mono` con `tabular-nums`.
  - Preview de subtítulos de impacto: `Barlow Condensed` / fuentes OFL de `assets/fonts/`.
- **Utilidades CSS del estudio:** scrollbars finos oscuros (`6px`), sliders `.studio-slider` con thumb ámbar `#F59E0B`, sombras de contorno `.caption-stroke` / `.caption-stroke-heavy` para preview de subtítulos y soporte `@media (prefers-reduced-motion: reduce)`.

## 2. Shell de navegación (todas las rutas)

- **Sidebar izquierda colapsable** (`240px` expandida, `68px` colapsada, `bg-[#0D0D10]`):
  - Marca con icono `W` en caja ámbar + `NEXT_PUBLIC_APP_NAME` (`WinClip`).
  - Píldora superior de estado del motor local (`M1 Local · Ready` / degradado según `/api/health`) clicable hacia `/settings/status`.
  - 5 ítems con contadores discretos en `font-mono`: **Proyectos**, **Campañas**, **Cuentas**, **Publicaciones**, **Ajustes / Estado**.
  - Pie con resumen de almacenamiento local (`STORAGE_DIR` real, sin rutas hardcodeadas).
- **TopBar (`h-14`):** título de sección, buscador global (`Buscar proyectos, clips, cuentas…`) y botón primario `+ Nuevo proyecto`.
- **Toasts:** notificaciones flotantes limpias (`sonner` estilizado con las mismas superficies `#141418` y bordes `white/[0.1]`).

## 3. Pantallas clave y ajustes respecto al prototipo

Los siguientes ajustes **sí deben incorporarse al implementar cada change** (el prototipo solo cubre el 95%):

| Pantalla | Change | Qué adoptar del prototipo | Ajustes obligatorios al implementar |
|---|---|---|---|
| `/projects` | 5 (`add-web-ui-cards`) | Strip superior de 3 métricas con divisores hairline, filtros de estado e idioma (`ES/EN`), toggle Grid 16:9 / Lista, barra de progreso en vivo en proyectos activos. | Añadir botón/menú **Eliminar proyecto** con diálogo de confirmación en cada card y fila; conectar al stream SSE real. |
| `/projects/new` | 5 (`add-web-ui-cards`) | Layout 2 columnas con **phone preview 9:16 sticky a la derecha** que refleja en vivo el preset (`bold-yellow`, `hormozi`, `clean-white`, `mrbeast`) y el modo de reframe (`face`, `center`, `blur`), pestañas `Pegar URL | Subir archivo` con dropzone y progreso, slider `1–20` + toggle `"Máximo posible"`. | Usar los IDs reales del backend (`bold-yellow`, `face`, `blur`, etc.), mencionar `"OpenCV YuNet"` (no MediaPipe) y `"H.264 VideoToolbox"` (`1080×1920`, `≤30fps`), y mantener el selector de campaña deshabilitado con aviso hasta el change 6. |
| `/projects/[id]` | 5 (`add-web-ui-cards`) | Stepper horizontal de 4 etapas (`Descarga → Transcripción → Selección IA → Render`) con botón cancelar; grid 3–4 cols de cards 9:16 con hover-play, score pill (`94/100`), checkbox multi-select, hook, hashtags, alertas de `rule_violations`, `EditTrimModal` split con waveform + sliders `In/Out` + preview, y barra flotante inferior al seleccionar clips. | Eliminar el toggle de demostración `"Simular en vivo / Completado"` (usar estado real SSE); en change 5 dejar el botón `"Publicar en redes →"` visible pero deshabilitado con tooltip hasta el change 8. |
| `/settings` y `/settings/status` | 5 (`add-web-ui-cards`) | Tarjetas oscuras de estado del motor local con badges `ok/warn/error` y botón de refresco. | Reemplazar los valores fijos del prototipo por los **checks reales de `GET /api/health`** (`winclip doctor`: ffmpeg-full 9.1, mlx-whisper, Ollama, almacenamiento en `STORAGE_DIR`, 4 claves LLM como presente/ausente, etc.). No mostrar controles simulados que no tengan endpoint. |
| `/campaigns` | 6 (`add-campaign-rules`) | Split con lista de campañas a la izquierda y editor a la derecha con pestañas `Formulario estructurado` \| `Pegar brief (IA)` (badge violeta `IA` en campos inferidos) + vista JSON sincronizada colapsable con botón copiar. | Añadir botón **Duplicar campaña**, selector de **Plantillas de ejemplo (ES/EN)**, campos `target_platforms` y `extra_instructions`, mapear `language` a `auto \| es \| en`, y usar **subida de PNG/WebP** para `watermark_path` (`/api/campaigns/watermarks`). |
| `/accounts` | 7 (`add-social-accounts`) | Secciones agrupadas por YouTube, TikTok e Instagram; tarjetas con avatar/iniciales, badge `API Oficial` (sky) vs `Playwright` (violet), estado `Conectada` / `Expirada` (borde rojo + CTA `Reconectar` ámbar), estrella `Default`, `Probar conexión`, modal `+ Conectar cuenta`. | Añadir opción **Importar token existente** (ruta local sin copiar al repo) y acción para **renombrar alias** de una cuenta ya conectada. |
| `/publications` y `PublishDialog` | 8 (`add-publishers`) | `PublishDialog` con cuentas agrupadas por plataforma (deshabilitando expiradas), tabs de metadatos por red, selector `Directo / Borrador Inbox` y programador fecha/hora. Tabla `/publications` con filtros con contadores, miniatura 9:16, enlace externo y modal `Ver captura` con error + `Reintentar`. | Añadir acción **Cancelar** en filas `Programadas` y filtro/estado `Cancelada`; en `PublishDialog` para YouTube incluir campos opcionales de `privacidad`, `tags` y `comentario fijado`. |
