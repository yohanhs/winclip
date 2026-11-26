# Tasks

## 1. Dependencias y utilidades base (`core`)

- [ ] 1.1 Añadir `yt-dlp`, `python-ulid` y `mlx-whisper` (con marcador `sys_platform == "darwin" and platform_machine == "arm64"`) a `apps/api/pyproject.toml` y registrar el marcador `slow` en la configuración de `pytest`. Verificar con `uv sync --project apps/api` y `uv run --project apps/api python -c "import yt_dlp, ulid"`.
- [ ] 1.2 Implementar `apps/api/winclip/core/ids.py` (generación de ULID en minúsculas y validación de `project_id` contra `^[a-z0-9][a-z0-9_-]{1,63}$`) y `apps/api/winclip/core/storage.py` (protocolo `Storage`, clase `LocalStorage` con rutas de proyecto de `docs/architecture.md §5`, prevención de path traversal y `write_json_atomic`). Verificar con tests unitarios en `apps/api/tests/test_storage_ids.py` ejecutando `uv run --project apps/api pytest tests/test_storage_ids.py`.
- [ ] 1.3 Definir los modelos Pydantic `SourceMeta`, `WordTimestamp`, `TranscriptSegment` y `Transcript` (contrato exacto `docs/architecture.md §6.1` y `source/meta.json` de `design.md`) más el tipo `ProgressCallback` en `apps/api/winclip/pipeline/schemas.py`. Verificar con tests de validación positiva y negativa (timestamps invertidos, probabilidad fuera de `[0,1]`) en `apps/api/tests/test_pipeline_schemas.py`.

## 2. Pipeline de ingesta (`media-ingest`)

- [ ] 2.1 Implementar el adaptador de descarga `yt-dlp` y las excepciones de dominio (`IngestError`, `InvalidUrlError`, `PrivateVideoError`, `LiveStreamNotSupportedError`, `MissingAudioError`, `ProjectExistsError`) en `apps/api/winclip/pipeline/ingest.py`, configurando formato MP4 <=1080p, `ffmpeg_location=FFMPEG_BIN`, detección previa de `is_live` y `progress_hook`. Verificar con tests unitarios mockeando `yt_dlp.YoutubeDL` para éxito, URL inválida, video privado y live en curso.
- [ ] 2.2 Implementar en `apps/api/winclip/pipeline/ingest.py` la ingesta de archivos locales (`.mp4`, `.mov`, `.mkv`, `.webm`), la inspección con `FFPROBE_BIN` (`source/meta.json`), la extracción de `audio/audio16k.wav` (mono 16 kHz PCM) con `FFMPEG_BIN`, el manejo de `--force` y el reporte de progreso. Verificar con tests en `apps/api/tests/test_ingest.py` usando un video sintético generado por `FFMPEG_BIN` (con audio y sin audio) y comprobando `audio16k.wav` con `FFPROBE_BIN`.

## 3. Pipeline de transcripción (`transcription`)

- [ ] 3.1 Implementar `apps/api/winclip/pipeline/transcribe.py` con el protocolo `TranscriberBackend`, adaptador perezoso para `mlx-whisper` (`word_timestamps=True`, soporte `--language es|en|auto`, `--model` con atajo `tiny`), normalización de palabras/timestamps, escritura atómica de `transcript/transcript.json`, reanudabilidad (`--force`) y callback de progreso. Verificar con tests unitarios en `apps/api/tests/test_transcribe.py` usando un backend falso que cubra contrato §6.1, autodetección/idioma forzado, `--model tiny`, reanudabilidad, `--force` y orden de progreso.
- [ ] 3.2 Añadir un test de integración marcado `@pytest.mark.slow` en `apps/api/tests/test_transcribe_slow.py` que genere/use un clip de audio corto real y ejecute `mlx-whisper` (con modelo `tiny`) validando `transcript.json` contra el esquema `Transcript`. Verificar en local (Mac M1) con `uv run --project apps/api pytest -m slow tests/test_transcribe_slow.py`.

## 4. Subcomandos CLI y documentación

- [ ] 4.1 Añadir los subcomandos `winclip ingest <source> [--project-id] [--force]` y `winclip transcribe <project_id> [--language] [--model] [--force]` en `apps/api/winclip/cli.py` con barra de progreso Rich, mensajes de error claros y códigos de salida no nulos ante fallos. Verificar con tests de `CliRunner` en `apps/api/tests/test_cli_pipeline.py` cubriendo flujos exitosos y de error.
- [ ] 4.2 Actualizar `README.md` documentando el uso de `winclip ingest` y `winclip transcribe` (ejemplos con URL y archivo local, flags `--project-id`, `--language`, `--model`, `--force` y estructura generada en `storage/projects/`). Verificar ejecutando `uv run --project apps/api winclip ingest --help && uv run --project apps/api winclip transcribe --help` y contrastando las opciones documentadas.

## 5. Verificación integrada

- [ ] 5.1 Ejecutar la verificación completa del change: `uv run --project apps/api ruff check . && uv run --project apps/api ruff format --check .`, `uv run --project apps/api pytest -m "not slow"`, probar el flujo encadenado `winclip ingest` → `winclip transcribe` sobre un video sintético en un `STORAGE_DIR` temporal, y ejecutar `openspec validate add-ingest-transcription --strict` sin errores.

## Workflow follow-up

- Revisión del orquestador y pruebas manuales con un video real en local (`pytest -m slow`).
- Archivar el change con `openspec archive add-ingest-transcription` tras la aprobación.
