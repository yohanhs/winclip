# Design

## Context

Véase `proposal.md` para la motivación. Este change se construye sobre `setup-foundation`, que ya proporciona `Settings` (`winclip/core/config.py`), el entry point CLI `winclip` (`winclip/cli.py`) y los binarios verificados en el entorno (`FFMPEG_BIN` = ffmpeg-full, `FFPROBE_BIN`, `WHISPER_MODEL` = `mlx-community/whisper-large-v3-turbo` en caché local sobre Mac M1 16 GB).

En esta fase aún no existe base de datos SQLite ni worker de jobs (ambos llegan en `add-api-jobs`), por lo que el estado de un proyecto vive íntegramente en disco bajo `STORAGE_DIR/projects/<project_id>/`. Los módulos del pipeline deben ser funciones puras y testeables desacopladas de la CLI para que el worker las invoque directamente más adelante.

## Goals / Non-Goals

**Goals:**
- Implementar `core/ids.py` y `core/storage.py` alineados con `docs/architecture.md §5` y `§8`.
- Entregar `pipeline/ingest.py` y `pipeline/transcribe.py` con contratos Pydantic estrictos, escrituras atómicas, manejo claro de errores y callback de progreso reutilizable por el worker.
- Mantener una suite de tests rápida ejecutable en CI (Linux o macOS sin GPU ni red) más un test de integración `slow` para validar transcripción real en M1.

**Non-Goals:**
- Registro de proyectos en SQLite o cola de jobs (`add-api-jobs`).
- Selección de clips con LLM (`add-clip-selection-llm`).
- Diarización de hablantes, traducción de transcripciones o captura de livestreams en directo.

## Contratos

Contratos nuevos introducidos por este change (complementan `docs/architecture.md` sin alterarlo):

### 1. `source/meta.json` (`SourceMeta` en `winclip/pipeline/schemas.py`)
```json
{
  "project_id": "01jex8z9abc123def456gh7890",
  "source_type": "url",
  "source_url": "https://www.youtube.com/watch?v=...",
  "original_filename": "original.mp4",
  "title": "Título del video",
  "channel": "HookVault",
  "uploader_id": "@hookvault",
  "duration": 612.4,
  "width": 1920,
  "height": 1080,
  "fps": 30.0,
  "video_codec": "h264",
  "audio_codec": "aac",
  "audio_sample_rate": 48000,
  "has_audio": true,
  "file_size_bytes": 123456789,
  "created_at": "2026-11-26T15:00:00Z"
}
```
Para archivos locales: `source_type = "file"`, `source_url = null`, `channel = null`, `uploader_id = null`, `title` = nombre del archivo sin extensión.

### 2. `transcript/transcript.json` (`Transcript`, `TranscriptSegment`, `WordTimestamp`)
Implementa exactamente `docs/architecture.md §6.1`:
- `language: str`, `duration: float`, `model: str`, `segments: list[TranscriptSegment]`.
- `TranscriptSegment`: `id: int`, `start: float`, `end: float`, `text: str`, `words: list[WordTimestamp]`.
- `WordTimestamp`: `w: str`, `s: float`, `e: float`, `p: float` (`0 <= s <= e`, `0.0 <= p <= 1.0`).

### 3. Callback de progreso (`ProgressCallback`)
```python
ProgressCallback = Callable[[float, str], None]  # (progress: 0.0..100.0, stage: str)
```
Compatible directamente con `job.progress` (`0–100`) y `job.stage` de `docs/architecture.md §7`. Etapas estándar:
- Ingesta: `download` (o `copy`), `probe`, `extract_audio`.
- Transcripción: `load_model`, `transcribe`, `save`.

### 4. Protocolo `Storage` (`winclip/core/storage.py`)
Respeta `docs/architecture.md §8` (`path(*parts) -> Path`) e implementa `LocalStorage(root: Path)` con utilidades de layout de proyecto (`project_dir`, `source_meta_path`, `audio_path`, `transcript_path`) y escritura atómica (`write_json_atomic` mediante archivo temporal en el mismo directorio + `os.replace`).

## Decisions

1. **IDs de proyecto con ULID en minúsculas (`python-ulid`) y validación estricta de `--project-id`.**
   - *Decisión:* generar IDs con `str(ULID()).lower()` (`core/ids.py`). Cuando el usuario pasa `--project-id`, validar contra `^[a-z0-9][a-z0-9_-]{1,63}$` y verificar que la ruta resuelta quede dentro de `STORAGE_DIR/projects/`.
   - *Alternativas:* `uuid4` (no es ordenable cronológicamente y contradice `docs/architecture.md §5`); implementación propia de ULID (innecesaria existiendo `python-ulid`).

2. **Descarga remota mediante el paquete Python `yt-dlp` (sin subproceso).**
   - *Decisión:* usar `yt_dlp.YoutubeDL` en un adaptador inyectable (`MediaDownloader`) con:
     - `format = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]"`
     - `merge_output_format = "mp4"`, `ffmpeg_location = settings.ffmpeg_bin`, `noplaylist = True`, `quiet = True`, `no_warnings = True`.
     - Comprobación previa con `extract_info(url, download=False)` para detectar `is_live=True` (`LiveStreamNotSupportedError`) antes de descargar.
     - Mapeo explícito de `DownloadError` a excepciones de dominio (`InvalidUrlError`, `PrivateVideoError`, `IngestError`) y `progress_hook` conectado al `ProgressCallback` (rango `0–65%` para descarga; `65–75%` para probe; `75–100%` para extracción de audio).
   - *Alternativas:* invocar `YTDLP_BIN` por subproceso (más frágil al parsear progreso y clasificar errores; `YTDLP_BIN` queda como respaldo documentado).

3. **Inspección y extracción de audio mediante subprocesos directos a `FFPROBE_BIN` y `FFMPEG_BIN`.**
   - *Decisión:* ejecutar `subprocess.run` sin shell usando siempre las rutas de `Settings`:
     - `FFPROBE_BIN -v error -print_format json -show_format -show_streams <video>` para extraer metadatos técnicos y verificar `has_audio`. Si no hay pista de audio, abortar con `MissingAudioError` antes de crear `source/meta.json`.
     - `FFMPEG_BIN -y -i <video> -vn -ac 1 -ar 16000 -c:a pcm_s16le <audio16k.wav>` para generar el WAV normalizado.
   - *Alternativas:* `ffmpeg-python` (proyecto sin mantenimiento activo y abstrae en exceso comandos simples); `pydub` (depende de `audioop`, eliminado en Python 3.13+, y no controla fácilmente el binario keg-only).

4. **Transcripción con `mlx-whisper` detrás de un protocolo inyectable (`TranscriberBackend`).**
   - *Decisión:* definir un backend inyectable para `pipeline/transcribe.py` cuya implementación por defecto realiza importación perezosa (*lazy import*) de `mlx_whisper` y llama a `mlx_whisper.transcribe(str(audio_path), path_or_hf_repo=model_repo, word_timestamps=True, language=None if language == "auto" else language)`.
   - Mapeo de `--model`: si es `tiny`, resolver a `mlx-community/whisper-tiny`; si se omite, usar `settings.whisper_model`; si se pasa un repo HF completo, usarlo tal cual.
   - Capa de normalización post-Whisper: limpiar espacios sobrantes en `w`, asegurar `0 <= s <= e` (ajustando `e = max(s, e)`), acotar `p` a `[0.0, 1.0]` (usando `1.0` si alguna palabra carece de probabilidad), renumerar `segments[].id` desde 0 en orden cronológico y tomar `duration` de `source/meta.json` (o último `end` como respaldo).
   - *Alternativas:* `faster-whisper` (no aprovecha MLX en Apple Silicon); importar `mlx_whisper` a nivel de módulo (rompería la importación y los tests en runners Linux de CI).

5. **Reanudabilidad y escritura atómica.**
   - *Decisión:* en `transcribe`, si `transcript/transcript.json` existe y valida contra el modelo Pydantic `Transcript` y `force=False`, devolverlo sin invocar el motor de transcripción. Si está corrupto o `force=True`, recalcular y escribir vía archivo temporal + `os.replace`. En `ingest`, si `source/meta.json` ya existe y `force=False`, fallar con `ProjectExistsError` para evitar sobrescrituras accidentales.
   - *Alternativas:* sobrescribir siempre en silencio (desperdicia minutos de GPU en videos largos o destruye datos previos).

6. **Justificación de nuevas dependencias en `apps/api/pyproject.toml`.**
   - `yt-dlp`: paquete Python oficial para descarga de video y metadatos (acordado en `docs/architecture.md §4`).
   - `python-ulid`: generación estándar de ULIDs en minúsculas (acordado en `docs/architecture.md §5`).
   - `mlx-whisper` con marcador de entorno `sys_platform == "darwin" and platform_machine == "arm64"`: motor de transcripción nativo para Apple Silicon M1 (`config.yaml` y `docs/architecture.md §4`), condicionado a macOS arm64 para que `uv sync` y CI en Linux sigan funcionando sin fallos.

7. **Estrategia de pruebas.**
   - *Tests rápidos (CI):* fixture que genera un video sintético corto (~2 s con patrón `testsrc` y tono `sine` de 440 Hz) usando `FFMPEG_BIN` en `tmp_path`; prueba `ingest` local end-to-end y valida `audio16k.wav` con `FFPROBE_BIN`. Las pruebas de URL usan un `MediaDownloader` falso para los escenarios de éxito, URL inválida, video privado y livestream. Las pruebas de transcripción usan un `TranscriberBackend` falso que ejercita normalización, `--language`, `--model tiny`, `--force`, reanudabilidad y callbacks de progreso.
   - *Test `slow` (local en M1):* marcado `@pytest.mark.slow`, transcribe un audio corto real con `mlx-whisper` (modelo `tiny` o `WHISPER_MODEL`) y valida el contrato `Transcript`.

## Risks / Trade-offs

- [YouTube cambia endpoints o exige autenticación/cookies en ciertos videos] → aislar la descarga en `MediaDownloader` y entregar mensajes de error claros; actualizar `yt-dlp` cuando cambien extractores sin tocar el resto del pipeline.
- [`mlx-whisper` no expone callback nativo por segmento para progreso continuo] → emitir hitos de etapa deterministas (`load_model` → `transcribe` → `save` → `100`) sin romper el contrato `ProgressCallback(0–100, stage)` que usará el worker en el change 4.
- [Diferencias entre macOS arm64 (local) y Linux x86_64 (CI)] → `mlx-whisper` se declara con marcador de entorno y se importa de forma perezosa; si se intenta transcribir en una plataforma sin `mlx-whisper` instalado, se lanza un error explícito en tiempo de ejecución.
- [Videos muy largos (>1 h) generan archivos `source/original.mp4` y `audio16k.wav` de varios cientos de MB] → copia/descarga por streaming sin cargar en RAM, audio PCM 16 kHz mono (~115 MB/hora) y limpieza de archivos temporales en caso de error.
