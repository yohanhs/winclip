# Proposal

## Why

Tras establecer la base del monorepo y el diagnóstico de dependencias en `setup-foundation`, WinClip necesita las dos primeras etapas ejecutables del pipeline: incorporar videos largos (desde URL remota o archivo local) y transcribirlos localmente con marcas temporales a nivel de palabra. Entregar estas capacidades primero vía CLI permite validar la calidad del audio y de `transcript.json` antes de construir la selección con LLM, el render y la API.

## What Changes

- Utilidades base en `apps/api/winclip/core/`: generación de identificadores ULID en minúsculas (`ids.py`) y abstracción de almacenamiento local (`storage.py`) siguiendo el layout por proyecto de `docs/architecture.md §5` y el protocolo `Storage` de `§8`.
- Pipeline de ingesta (`pipeline/ingest.py`) y comando CLI `winclip ingest <url|ruta> [--project-id <id>] [--force]`:
  - Descarga videos desde URLs soportadas eligiendo el mejor formato MP4 hasta 1080p y capturando metadatos (título, canal, duración), con manejo explícito de URL inválida, video privado y directos en curso.
  - Copia archivos locales (`.mp4`, `.mov`, `.mkv`, `.webm`) al proyecto sin alterar el archivo original.
  - Inspecciona el video con `FFPROBE_BIN` para generar `source/meta.json` y extrae audio WAV PCM mono 16 kHz en `audio/audio16k.wav` usando `FFMPEG_BIN`.
- Pipeline de transcripción (`pipeline/transcribe.py`) y comando CLI `winclip transcribe <project_id> [--language es|en|auto] [--model <id|tiny>] [--force]`:
  - Transcribe `audio/audio16k.wav` localmente con marcas temporales por palabra (`word_timestamps`), generando `transcript/transcript.json` exacto al contrato `docs/architecture.md §6.1`.
  - Soporta callback de progreso normalizado (`0–100`), modelo ligero opcional (`tiny`) y reanudabilidad automática (no recalcula si ya existe `transcript.json` válido salvo con `--force`).
- Suite de tests unitarios e integración rápidos (con video sintético generado por `FFMPEG_BIN` y backend de transcripción simulado) más test de integración marcado `slow` sobre audio corto real, y actualización del `README.md` con el uso de ambos comandos.

**Fuera de alcance:** persistencia en SQLite/SQLModel, cola de jobs y worker, endpoints HTTP o SSE (llegan en `add-api-jobs`), interfaz web, selección de clips con LLM (`add-clip-selection-llm`), diarización de hablantes, traducción de audio y soporte de transmisiones en directo en curso.

## Capabilities

### New Capabilities
- `media-ingest`: ingesta de videos largos desde URL remota o archivo local en un proyecto aislado en disco, extracción de metadatos técnicos y generación de audio normalizado mono a 16 kHz.
- `transcription`: transcripción local con marcas temporales por palabra en español, inglés o detección automática, persistida según el contrato `transcript.json` con soporte de reanudabilidad y reporte de progreso.

### Modified Capabilities

## Impact

- Código nuevo en `apps/api/winclip/core/` (`ids.py`, `storage.py`), `apps/api/winclip/pipeline/` (`schemas.py`, `ingest.py`, `transcribe.py`) y tests en `apps/api/tests/`.
- Código modificado: `apps/api/winclip/cli.py` (nuevos subcomandos `ingest` y `transcribe`), `apps/api/pyproject.toml` y `README.md`.
- Dependencias Python nuevas: `yt-dlp`, `python-ulid` y `mlx-whisper` (restringida a macOS arm64 para no romper CI en Linux).
- Artefactos en disco bajo `STORAGE_DIR/projects/<project_id>/{source,audio,transcript}/` (ya excluidos de git).
