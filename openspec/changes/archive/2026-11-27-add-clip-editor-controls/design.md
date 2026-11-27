# Design

## Context

Los changes 3, 4 y 5 dejaron listo el pipeline de render (`pipeline/render.py`, `pipeline/reframe.py`, `pipeline/subtitles/`), los endpoints `PATCH /api/clips/{id}` y `POST /api/clips/{id}/rerender`, y el editor modal `clip-trim-dialog.tsx` / `clip-edit-dialog.tsx` en `/projects/[id]`. Actualmente, el worker siempre pasa al render el `subtitle_preset` y `reframe_mode` del proyecto, sin permitir overrides por clip ni corrección puntual de palabras mal transcritas por Whisper. Véase `proposal.md` para la motivación.

## Goals / Non-Goals

**Goals:**
- Reutilizar los parámetros que `pipeline/render.py` (`RenderOptions`: `preset`, `reframe`, `crop_x_pct`, `crop_y_pct`, `zoom_pct`) ya soporta desde el change 3.
- Persistir correcciones de subtítulos por clip de forma no destructiva (sin tocar `transcript.json` del proyecto) para que restablecer o cambiar el tramo `start`/`end` siga siendo seguro.
- Mantener la estética oscura de `docs/ui-design.md` dentro del editor de clips sin añadir complejidad multipista.

**Non-Goals:**
- Edición de timestamps individuales de palabras ni añadir/eliminar palabras con nueva sincronización de audio.
- Edición de múltiples pistas, audio o B-roll.
- Dependencias nuevas en Python ni JS.

## Contratos

- **Extensiones en la tabla `clip` (migración Alembic):**
  - `render_overrides`: JSON nullable (`{"subtitle_preset": str | None, "reframe_mode": str | None, "crop_x_pct": float | None, "crop_y_pct": float | None, "zoom_pct": float | None}`).
  - `subtitle_overrides`: JSON nullable (diccionario `dict[str, str]` mapeando índice de palabra del clip `"0"`, `"1"`, ... — o clave estable `f"{start_ms}:{end_ms}"` — al texto corregido).
- **Endpoint nuevo:**
  - `GET /api/clips/{id}/words` (`operationId="getClipWords"`) → `{"clip_id": str, "words": [{"key": str, "index": int, "original": str, "text": str, "start": float, "end": float, "edited": bool}]}`.
- **Extensión de `ClipUpdate` (`PATCH /api/clips/{id}`) y `ClipOut`:**
  - Campos opcionales: `subtitle_preset`, `reframe_mode`, `crop_x_pct`, `crop_y_pct`, `zoom_pct`, `subtitle_overrides`.

## Decisions

1. **Clave estable por timestamp `(start_ms, end_ms)` para `subtitle_overrides`.**
   - *Por qué:* si el usuario edita una palabra y luego recorta `start_sec` 2 segundos antes con la mini-timeline, los índices posicionales `0, 1, 2` se desplazarían y aplicarían la corrección a otra palabra. Usar la clave `f"{round(w.s * 1000)}:{round(w.e * 1000)}"` mantiene cada corrección anclada exactamente a su palabra aunque cambien `start_sec`/`end_sec`.
   - *Alternativa descartada:* guardar una copia completa del subarray de palabras (se desincroniza al ampliar el tramo `start`/`end` en la mini-timeline).
2. **Resolución en cascada de opciones de render en `worker/handlers.py`.**
   - *Orden:* `clip.render_overrides` > `campaign.rules` (cuando exista) > `project` (`subtitle_preset`, `reframe_mode`) > defaults de `RenderOptions`. La huella `.render.sha256` del change 3 incluye el contenido de `subs.ass` / `subtitle_overrides` y `RenderOptions`, garantizando que cualquier corrección o cambio de crop dispare un re-render real.
3. **Unificación ergonómica en el modal de edición de clip (`clip-trim-dialog.tsx`).**
   - Organizar el panel derecho del modal en 3 pestañas limpias (`Recorte y metadatos`, `Subtítulos`, `Cámara / Estilo`) manteniendo el preview 9:16 fijo a la izquierda y un único botón `"Guardar y Re-renderizar"`, siguiendo el lenguaje visual de `docs/ui-design.md`.
4. **Sin nuevas dependencias:** todo usa SQLModel, Alembic, Pydantic, `RenderOptions` existente y componentes `shadcn/ui` ya instalados (`tabs`, `slider`, `select`, `input`).

## Risks / Trade-offs

- [Corregir una palabra corta por una frase muy larga puede alterar el ancho de línea en subtítulos] → El ajuste automático por ancho en píxeles de `subtitles/layout.py` y `ass_engine.py` (change 3) ya re-agrupa o escala para evitar desbordamientos; limitar cada override a 64 caracteres en validación Pydantic.
- [Vista previa de `crop_x`/`crop_y`/`zoom` en la web sin decodificar video en el cliente] → Mostrar un recuadro guía de recorte 9:16 aproximado sobre la miniatura o preview en el modal; el resultado exacto se ve inmediatamente tras el re-render (~15 s en M1).
