# Design

## Context

Ver `proposal.md` para la motivación y alcance. Este change es el último de la fase CLI-only (changes 1–3 en `docs/architecture.md §2`): consume `source/original.<ext>`, `source/meta.json`, `transcript/transcript.json` (§6.1) y `selection/candidates.json` (§6.2), y produce `clips/<clip_id>/{clip.mp4,thumb.jpg,subs.ass,render.json}` (§6.3).

Restricciones verificadas del entorno:
- Hardware objetivo: Apple Silicon M1 16 GB, macOS, Python 3.12 (`uv`).
- `FFMPEG_BIN=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg` (keg-only con `libass`, `freetype`, `harfbuzz`, `h264_videotoolbox`) y `FFPROBE_BIN`. Nunca usar `ffmpeg` del PATH.
- Fuentes OFL base ya disponibles en `assets/fonts/` desde `setup-foundation` (Montserrat, Poppins, Anton, Bebas Neue, League Spartan, Inter); `Noto Color Emoji` se añade aquí tal como se acordó en `setup-foundation/design.md`. Las fuentes comerciales del usuario (p. ej. Gotham) se cargan únicamente en local desde `USER_FONTS_DIR` (`~/Library/Fonts`).
- CI en GitHub Actions corre sobre Linux (sin `h264_videotoolbox` ni `~/Library/Fonts`), por lo que tests y codificación deben soportar respaldo a software cuando VideoToolbox no exista.

## Goals / Non-Goals

**Goals:**
- Módulos puros y testeables en `apps/api/winclip/pipeline/` (`reframe.py`, `subtitles/`, `render.py`) invocables tanto desde `winclip render` como desde el worker de `add-api-jobs` sin acoplarse a Typer ni FastAPI.
- Salida `render.json` 100 % conforme al contrato `docs/architecture.md §6.3`.
- Una sola pasada de codificación `ffmpeg` por clip para cumplir la meta de `< 60 s` por clip de `60 s` en M1.
- Cobertura de pruebas rápida y determinista (golden files `.ass` y fotogramas sintéticos) más integración `@pytest.mark.slow` con video generado por `testsrc2`.

**Non-Goals:**
- Persistencia en SQLite (`clip`, `job`) o endpoints REST/SSE (pertenecen a `add-api-jobs`).
- Detección de hablante activo por sincronía labial (Active Speaker Detection con audio+video); en este change el criterio multi-rostro usa área, centralidad y continuidad temporal.
- Generación automática de emojis por LLM o diccionarios (solo se diseña el punto de extensión en el modelo de cues).

## Decisions

### 1. Detector de rostros: OpenCV YuNet (`cv2.FaceDetectorYN`) frente a MediaPipe
- **Decisión:** Usar `opencv-python-headless` con el modelo ligero **YuNet** (`face_detection_yunet_2023mar.onnx`, ~230 KB, licencia MIT de OpenCV Zoo), abstraído tras un protocolo `FaceDetector` en `reframe.py`.
- **Justificación:**
  - `opencv-python-headless` ofrece wheels nativos estables para macOS arm64 y Linux en Python 3.12 sin arrastrar Qt/GUI ni conflictos de `protobuf`/`absl`/`flatbuffers`.
  - YuNet corre en ~3–5 ms por fotograma escalado a 640 px de ancho en CPU de M1 (~0.8–1.2 s para 180 muestras de un clip de 60 s a 3 fps), devuelve cajas con confianza y 5 puntos clave y rinde bien en planos medios y ligeros perfiles.
  - Además, OpenCV ya nos da histogramas HSV para detección de cambios de plano y varianza del Laplaciano para medir nitidez al elegir `thumb.jpg`, evitando añadir otra librería de visión.
- **Gestión del modelo ONNX:** Para mantener el repositorio público libre de pesos binarios (respetando `docs/architecture.md §3`), `face_detection_yunet_2023mar.onnx` se descarga bajo demanda en `STORAGE_DIR/models/` la primera vez que se ejecuta el modo `face` con verificación de SHA-256 (y permite ruta local vía variable opcional en tests). Los tests unitarios inyectan un `FaceDetector` sintético para correr offline en milisegundos.
- **Alternativa descartada:** `mediapipe` (BlazeFace). En versiones recientes depreca `mp.solutions` en favor de `mp.tasks` (que igual requiere archivo `.tflite` externo), introduce más dependencias transitivas y tiene menor margen en planos abiertos con rostros pequeños.

### 2. Algoritmo de trayectoria vertical, suavizado y cambios de plano
- **Muestreo:** Extraer fotogramas del rango `[start, end]` a `3 fps` por defecto (configurable `2–4 fps`), escalados a ancho `640 px` (manteniendo relación de aspecto) mediante un subproceso ligero de `FFMPEG_BIN` leyendo frames crudos (`rawvideo` BGR24) por pipe — más rápido y preciso en seek que `cv2.VideoCapture` en contenedores con B-frames.
- **Detección de cambios de plano:** Comparar histogramas HSV normalizados (correlación de Bhattacharyya / chi-cuadrado) entre muestras consecutivas. Cuando la distancia supera el umbral (default `0.45`), se abre un nuevo segmento de plano.
- **Selección del rostro principal:** Si hay varios rostros con confianza >= `0.6`, puntuar por `0.55 * area_norm + 0.25 * (1 - abs(cx - prev_cx)) + 0.20 * (1 - abs(cx - 0.5))` (en el primer frame de un plano se omite el término de continuidad). Esto prioriza al hablante en primer plano y evita saltos erráticos entre co-presentadores.
- **Suavizado por plano:** Dentro de cada segmento de plano:
  1. Interpolar huecos breves sin detección (< `1.0 s`) entre detecciones válidas; si un plano completo carece de rostros (o < 15 % de cobertura), respaldar a `x_norm = 0.5`.
  2. Aplicar banda muerta (`deadband = 0.02` del ancho) + filtro EMA bidireccional (ida y vuelta, cero desfase temporal) con `alpha = 0.25`.
  3. Aplicar límite de velocidad máxima (`max_speed = 0.22` del ancho fuente por segundo).
  4. Simplificar con Ramer-Douglas-Peucker (`epsilon = 0.005`) preservando los puntos exactos antes y después de cada corte de plano.
- **Alternativa descartada:** Savitzky-Golay vía `scipy.signal`. Evitar `scipy` ahorra ~100 MB de dependencia; EMA bidireccional + deadband + clamp de velocidad logra suavidad equivalente en ~40 líneas de Python/NumPy y se adapta trivialmente a planos cortos de 2–3 muestras.
- **Detección de video ya vertical:** Si `src_height > src_width` y `abs((src_width / src_height) - (9 / 16)) <= 0.08`, se salta el recorte horizontal, se escala/ajusta a `1080x1920` y se registra `reframe = {"mode": "passthrough", "track": []}` en `render.json`.

### 3. Ejecución en una sola pasada con `-filter_complex_script`
- **Decisión:** Construir un grafo `filter_complex` escrito a un archivo temporal y pasado a `FFMPEG_BIN` con `-filter_complex_script <path>`, combinando en una única ejecución:
  1. Recorte dinámico (`face`), estático (`center` con `crop_x_pct`/`crop_y_pct`/`zoom_pct`), fondo desenfocado (`blur`) o escalado (`passthrough`).
  2. Overlay de hook (si está activo) mediante una única imagen PNG RGBA generada con Pillow (ver Decisión 6).
  3. Overlay de marca de agua (si se especifica `--watermark`).
  4. Quemado de subtítulos: filtro `ass=filename=<subs.ass>:fontsdir=<tmp_fontsdir>` en motor `ass`, o entrada secundaria `rawvideo` RGBA por pipe + `overlay` en motor `pil`.
  5. Cadena de audio en la misma pasada: `loudnorm=I=-14:TP=-1.5:LRA=11` + `-c:a aac -b:a 192k -ar 48000 -ac 2`.
- **Recorte dinámico suave por fotograma:** En modo `face`, la trayectoria simplificada a segmentos `[t_i, t_{i+1}]` se traduce a una expresión piecewise-linear para `x` del filtro `crop`, con saltos instantáneos en los cortes de plano. Al ir dentro de `-filter_complex_script` nunca choca con límites de longitud de argumentos del shell.
- **Alternativa descartada:** Dos pasadas (cortar+reencuadrar a archivo intermedio y luego quemar subtítulos) o `loudnorm` en dos pasadas. Duplicaría el I/O y el tiempo de codificación, poniendo en riesgo la meta de `< 60 s` en M1. Para clips cortos de 15–60 s, `loudnorm` de una pasada ofrece normalización estable a `-14 LUFS`.

### 4. Subtítulos: motor `ass` por defecto y motor `pil` alternativo
- **Agrupación compartida (`subtitles/layout.py`):** Ambos motores consumen la misma lista de `SubtitleCue` (con `words: list[TimedWord]`, `lines: list[list[TimedWord]]`, `emoji: str | None = None`). Las reglas de corte (puntuación, `max_chars_per_line`, `max_words_per_cue`, `max_lines <= 2`, `max_pause_sec`, `uppercase`) vienen del preset JSON y respetan la heurística probada de `subtitulos_quemar.py` en `bold-yellow`.
- **Por qué eventos por palabra en `ass` en lugar de `\k`:** Las etiquetas karaoke estándar `\k`/`\kf` de ASS rellenan acumulativamente de izquierda a derecha y no permiten animar escala (`\fscx`/`\fscy`) solo sobre la palabra en curso. Generar un evento `Dialogue` por cada intervalo de palabra activa —marcando exclusivamente esa palabra con `{\c&H...&\t(0,80,\fscx112\fscy112)}`— replica fielmente el estilo moderno de Shorts/Reels/Hormozi/MrBeast, evita artefactos de solape y produce archivos `.ass` limpios para tests golden.
- **Resolución de fuentes y `fontsdir` (`subtitles/fonts.py`):**
  1. Indexa fuentes en `USER_FONTS_DIR` (si existe; solo local) y recursivamente en `assets/fonts/`.
  2. Si la fuente pedida (preset o `--font`) existe, la selecciona; si falta, emite `warning` y usa `preset.fallback_font` (siempre una OFL de `assets/fonts/`).
  3. Para `libass`, crea un directorio temporal con enlaces simbólicos a los archivos `.ttf`/`.otf` de `assets/fonts/` y, si aplica, la fuente local resuelta, pasando ese directorio en `fontsdir=...`. Esto garantiza portabilidad y evita tocar la configuración de fuentes del sistema.
- **Optimización del motor `pil` (`subtitles/pil_engine.py`):** Portado del enfoque de `subtitulos_quemar.py` (Pillow + NumPy con contorno y sombra). En lugar de decodificar y re-codificar el video completo en Python (lento en M1), `pil` renderiza **únicamente una capa RGBA transparente** por cada estado distinto de palabra (~100–200 renders de Pillow por clip de 60 s, cacheados por estado) y los envía por pipe (`-f rawvideo -pix_fmt rgba -s 1080x1920 -r <fps> -i pipe:0`) a `FFMPEG_BIN` para componerlos con `overlay` y codificar por hardware. Además, en modo `pil` siempre se escribe igualmente `subs.ass` para cumplir el contrato de archivos de salida del clip.

### 5. Codificación H.264: `h264_videotoolbox` con respaldo en CI
- **Decisión:** Detectar si `FFMPEG_BIN` soporta `h264_videotoolbox` en el host actual (probando `-encoders` y disponibilidad del dispositivo en macOS). En Apple Silicon M1 se usa `-c:v h264_videotoolbox -b:v 10M -maxrate 14M -bufsize 20M -profile:v high -pix_fmt yuv420p -movflags +faststart`. Si no está disponible (por ejemplo, runners Linux de CI), se recurre automáticamente a `-c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -movflags +faststart`.
- **Justificación:** `10M` en `h264_videotoolbox` entrega excelente nitidez en `1080x1920@30fps` (~75 MB/min frente a ~180 MB/min de `24M`) y codifica un clip de 60 s en ~6–12 s en M1.
- **FPS de salida:** `out_fps = min(30, round(src_fps))` cuando `src_fps > 30`, o `src_fps` (redondeado al entero estándar o conservando `24`/`25`/`29.97`→`30`) cuando `src_fps <= 30`, reflejado en `render.json`.

### 6. Overlay de hook, marca de agua y miniatura `thumb.jpg`
- **Hook overlay:** En lugar de usar `drawtext` (propenso a errores de escape con comillas, dos puntos y saltos de línea en español/inglés), se renderiza **una sola imagen PNG RGBA** (`1080x1920`) con Pillow usando la fuente resuelta (tarjeta semitransparente con bordes redondeados y texto centrado con ajuste de línea en la zona superior segura `y ≈ 0.14–0.22 H`), superpuesta en la misma pasada de `ffmpeg` durante `[0, hook_seconds]` (default `3.0 s`, con fade-out de `0.3 s`). Funciona de forma idéntica en los motores `ass` y `pil`.
- **Marca de agua:** Si `--watermark <path>` está presente, se escala proporcionalmente a un ancho máximo de `190 px` (~17.5 % del ancho) y se coloca en la esquina superior derecha con margen seguro (`x=W-w-48:y=120`) y opacidad `0.7` dentro del mismo `filter_complex`.
- **Miniatura (`thumb.jpg`):** Durante el muestreo de reencuadre (o en 5 muestras equiespaciadas del clip en modos `center`/`blur`/`passthrough`), se selecciona el fotograma con mayor puntuación `face_conf * log1p(laplacian_var)` (descartando frames casi negros con luminancia media < 15). Se extrae ese instante exacto desde `clip.mp4` ya renderizado (asegurando que coincide con el encuadre final, o aplicando el encuadre sin subtítulos si se prefiere; extraer de `clip.mp4` fuera del primer fotograma con un comando `ffmpeg -ss <t> -vframes 1 -q:v 2` toma < 80 ms y produce exactamente `1080x1920`). Para evitar que los subtítulos tapen el rostro en la miniatura o elegir limpiamente el mejor instante, se extrae el instante seleccionado del propio `clip.mp4` (donde los subtítulos están en la zona inferior `0.66 H` y el rostro en la mitad superior).

### 7. Idempotencia y escrituras atómicas preservando `render.json` §6.3
- **Decisión:** `render.json` conserva **estrictamente** los 11 campos de `docs/architecture.md §6.3` sin añadir campos extra. La huella de idempotencia (`sha256` sobre: ruta+mtime+tamaño de la fuente, `candidate.{id,start,end,hook}`, modo y parámetros de reframe, motor, contenido JSON del preset, fuente resuelta, `hook_overlay`+`hook_seconds`, hash de `watermark`) se guarda en un archivo oculto `.render.sha256` dentro de `clips/<clip_id>/`.
- Al invocar render para un `candidate_id`:
  - Se buscan directorios existentes en `clips/*/render.json` cuyo `candidate_id` coincida.
  - Si existe y `.render.sha256` coincide y los 4 archivos (`clip.mp4`, `thumb.jpg`, `subs.ass`, `render.json`) están presentes y no vacíos, se omite el render salvo `--force`.
  - Si hay que renderizar (nuevo, parámetros distintos o `--force`), se reutiliza el `clip_id` existente (o se genera un ULID nuevo vía `core/ids.py`), se escribe todo en un directorio temporal hermano `.tmp-<ulid>/` y al terminar con éxito se reemplaza atómicamente `clips/<clip_id>/`.

### 8. Progreso reportable (`-progress pipe:1`)
- La función pública `render_clip(..., on_progress: Callable[[RenderProgress], None] | None = None)` emite `RenderProgress(clip_id, candidate_id, stage, percent, message)` con fases ponderadas: `reframe` (0–20 %), `subtitles` (20–30 %), `encode` (30–95 %, parseando `out_time_us` de `ffmpeg -progress pipe:1` en streaming línea a línea), `thumbnail` (95–100 %). La CLI conecta este callback a una barra Rich; en `add-api-jobs` el worker lo conectará a SQLite + SSE.

### 9. Nuevas dependencias justificadas
| Dependencia | Uso | Justificación |
|---|---|---|
| `opencv-python-headless` | Detección facial YuNet, histogramas de cambio de plano, nitidez Laplaciana y generación de fotogramas sintéticos en tests | Wheels arm64/Linux estables en Python 3.12, sin GUI, cubre 3 necesidades con una sola dependencia |
| `pillow` | Motor de subtítulos `pil`, tarjeta PNG de hook overlay y validación de `thumb.jpg` | Estándar en Python para tipografía TrueType + alfa RGBA; port directo de `subtitulos_quemar.py` |
| `numpy` | Buffers de fotogramas, suavizado numérico de trayectoria y composición RGBA en `pil` | Dependencia ya requerida por OpenCV; permite implementar EMA+RDP sin añadir `scipy` |

## Contratos

### A. `render.json` (referencia exacta a `docs/architecture.md §6.3`)
No se modifica el contrato; el modelo Pydantic `RenderManifest` valida exactamente:
```json
{
  "clip_id": "01j...",
  "candidate_id": "01j...",
  "width": 1080,
  "height": 1920,
  "fps": 30,
  "reframe": {"mode": "face", "track": [[0.0, 0.42], [1.0, 0.45]]},
  "subtitles": {"engine": "ass", "preset": "bold-yellow", "font": "Montserrat ExtraBold"},
  "hook_overlay": true,
  "duration": 48.6,
  "output": "clip.mp4",
  "thumbnail": "thumb.jpg"
}
```
Valores válidos de `reframe.mode`: `"face" | "center" | "blur" | "passthrough"`. `reframe.track` contiene pares `[t_sec, x_norm]` (lista vacía `[]` en `blur` y `passthrough`, `[[0.0, x_norm]]` en `center`, trayectoria muestreada/clave en `face`).

### B. Esquema de preset de subtítulos (`assets/subtitle-presets/<name>.json`)
```json
{
  "name": "bold-yellow",
  "description": "Estilo karaoke alto contraste blanco con palabra activa en amarillo",
  "font": "Montserrat ExtraBold",
  "fallback_font": "Montserrat ExtraBold",
  "font_size": 76,
  "uppercase": false,
  "primary_color": "#FFFFFF",
  "highlight_color": "#FFD600",
  "outline_color": "#000000",
  "outline_width": 6,
  "shadow_color": "#000000",
  "shadow_depth": 3,
  "highlight_scale_pct": 112,
  "y_pct": 0.66,
  "margin_x": 90,
  "max_lines": 2,
  "max_chars_per_line": 38,
  "max_words_per_cue": 7,
  "max_pause_sec": 0.65,
  "box_bg_color": null
}
```
Presets incluidos:
- `bold-yellow`: estilo del usuario (`#FFFFFF` + `#FFD600`, borde negro `6`, `y_pct: 0.66`, `max_chars_per_line: 38`, `max_words_per_cue: 7`, `uppercase: false`, fuente `Montserrat ExtraBold`, sobrescribible en local con `--font GothamBlack`).
- `hormozi`: `uppercase: true`, `max_words_per_cue: 3`, `max_chars_per_line: 20`, `#FFFFFF` + `#FFE500`, borde `8`, `highlight_scale_pct: 118`, `Montserrat Black`.
- `clean-white`: `uppercase: false`, `max_words_per_cue: 6`, `max_chars_per_line: 32`, `#FFFFFF` + `#38BDF8`, borde `3`, sombra suave, `box_bg_color: "#00000088"`, `Poppins Bold`.
- `mrbeast`: `uppercase: true`, `max_words_per_cue: 3`, `max_chars_per_line: 18`, `#FFFFFF` + `#FFD600`, borde `9`, `highlight_scale_pct: 120`, `Anton`.

### C. Interfaz Python del pipeline (para CLI y futuro worker)
```python
@dataclass(frozen=True)
class RenderProgress:
    clip_id: str
    candidate_id: str
    stage: Literal["reframe", "subtitles", "encode", "thumbnail"]
    percent: float  # 0.0 .. 100.0
    message: str

class RenderOptions(BaseModel):
    preset: str = "bold-yellow"
    reframe: Literal["face", "center", "blur"] = "face"
    engine: Literal["ass", "pil"] = "ass"
    font: str | None = None
    crop_x_pct: float = Field(default=50.0, ge=0.0, le=100.0)
    crop_y_pct: float = Field(default=50.0, ge=0.0, le=100.0)
    zoom_pct: float = Field(default=100.0, ge=100.0, le=300.0)
    hook_overlay: bool = True
    hook_seconds: float = Field(default=3.0, ge=0.5, le=10.0)
    watermark_path: Path | None = None
    force: bool = False
    sample_fps: float = Field(default=3.0, ge=2.0, le=4.0)

def render_clip(
    project_id: str,
    candidate_id: str,
    options: RenderOptions,
    *,
    settings: Settings | None = None,
    on_progress: Callable[[RenderProgress], None] | None = None,
) -> RenderManifest: ...
```

### D. Subcomando CLI
`winclip render <project_id> [--clip <candidate_id> | --all] [--preset bold-yellow] [--reframe face|center|blur] [--engine ass|pil] [--font <nombre>] [--crop-x-pct 50] [--crop-y-pct 50] [--zoom-pct 100] [--hook-overlay/--no-hook-overlay] [--hook-seconds 3.0] [--watermark <ruta>] [--force]`

## Risks / Trade-offs

- [Descarga inicial de YuNet ONNX sin conexión a internet] → El archivo se cachea una sola vez en `STORAGE_DIR/models/` con verificación SHA-256; si no hay red y no está en caché, se informa claramente cómo descargarlo o usar `--reframe center|blur`. Los tests unitarios usan detector inyectado y no requieren red.
- [Diferencias de nombres de fuente entre archivo `.ttf` y familia interna en `libass` / CoreText] → El índice de `subtitles/fonts.py` lee el nombre de familia/postscript real de la tabla `name` del TTF/OTF (vía Pillow `ImageFont.getname()`) para que `Style: ...` en `.ass` coincida exactamente con lo que `libass` espera en `fontsdir`.
- [Rendimiento del motor `pil` frente a `ass` en clips largos] → Al cachear los buffers RGBA por palabra activa y alimentar solo el stream de overlay a `ffmpeg` con `h264_videotoolbox`, el overhead de Python queda muy acotado; aun así `ass` sigue siendo el motor por defecto por ser ~3–5× más rápido.
- [Clips con múltiples hablantes en cuadro amplio tipo podcast] → El criterio área+centralidad+continuidad puede quedarse en el hablante más cercano cuando dos hablan a la vez; se mitiga con el modo `blur` o `center` manual y queda la puerta abierta a Active Speaker Detection en un change futuro.
- [Variabilidad de `loudnorm` de una pasada en clips muy cortos (< 5 s)] → Los candidatos de WinClip tienen duración mínima configurada (típicamente >= 15 s); para clips de prueba muy cortos (< 3 s) `loudnorm` igual completa sin fallar aunque la medición de LRA sea aproximada.
