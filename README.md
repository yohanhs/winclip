# WinClip

WinClip (nombre de código; la marca visible se configura con `APP_NAME`) es una aplicación **local** de
clipping: a partir de un vídeo largo (URL o archivo) genera cortes verticales 9:16 con subtítulos
palabra a palabra, siguiendo las reglas de una campaña, los revisa en una web y los publica en cuentas
de YouTube, TikTok e Instagram ya configuradas.

> Estado: **fundamentos e ingesta/transcripción (CLI)**. Este repositorio contiene el monorepo, la
> configuración central, el diagnóstico del sistema, el esqueleto de la web y las dos primeras etapas
> del pipeline. La selección, el render y la publicación llegan en los siguientes changes de OpenSpec.

## Requisitos

- macOS en Apple Silicon (objetivo: M1, 16 GB).
- [Node.js](https://nodejs.org) 24+ (hay `.nvmrc` con `24`) y [pnpm](https://pnpm.io) 10+.
- [uv](https://docs.astral.sh/uv/) (gestiona Python 3.12 automáticamente).
- `ffmpeg-full` de Homebrew **con libass** (keg-only, no está en el `PATH`):

  ```bash
  brew install ffmpeg-full
  # FFMPEG_BIN=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
  ```

- `yt-dlp` (`brew install yt-dlp`).
- Opcionales: Ollama con modelos locales y Playwright/Chromium para publicar sin API.

## Puesta en marcha

```bash
pnpm install                 # dependencias JS del monorepo
cp .env.example .env         # configuración local (ignorada por git)
pnpm dev                     # API en :8000 y web en :3000
```

- Web: <http://localhost:3000> · Estado del sistema: <http://localhost:3000/settings/status>
- API: <http://localhost:8000/api/health>

## Diagnóstico

```bash
uv run --project apps/api winclip doctor
```

Comprueba ffmpeg-full (filtros `ass` y `subtitles`), ffprobe, yt-dlp, el modelo Whisper en la caché de
Hugging Face, Ollama, Chromium de Playwright, el volumen externo y que `STORAGE_DIR` sea escribible.
Los servicios opcionales solo generan `warn`; un `error` hace que el comando termine con código 1.
Las claves de API se muestran únicamente como `presente`/`ausente`, nunca su valor.

## Pipeline: ingesta y transcripción (CLI)

Los changes 1–3 se validan solo por CLI antes de construir la API y la web.

```bash
# URL remota (mejor MP4 <= 1080p) o archivo local (.mp4, .mov, .mkv, .webm)
uv run --project apps/api winclip ingest "https://www.youtube.com/watch?v=..."
uv run --project apps/api winclip ingest /ruta/video.mov --project-id mi-proyecto

# transcripción local con timestamps por palabra
uv run --project apps/api winclip transcribe mi-proyecto --language es
uv run --project apps/api winclip transcribe mi-proyecto --model tiny --force
```

- `ingest [--project-id <id>] [--force]`: descarga o copia el video, inspecciona con `FFPROBE_BIN`
  (`source/meta.json`) y extrae `audio/audio16k.wav` (WAV PCM mono 16 kHz) con `FFMPEG_BIN`.
  `--project-id` acepta `[a-z0-9_-]` (2–64 caracteres); si se omite se genera un ULID en minúsculas.
  Sin `--force` un proyecto ya ingestado se rechaza para no sobrescribirlo.
- `transcribe [--language es|en|auto] [--model <repo|tiny>] [--force]`: transcribe en local con
  `mlx-whisper` (`word_timestamps=True`). Por defecto usa `WHISPER_MODEL` y autodetecta el idioma.
  Reutiliza `transcript/transcript.json` si ya es válido salvo con `--force`.

Cada proyecto queda aislado bajo `STORAGE_DIR/projects/<project_id>/`:

```
source/original.<ext>       video descargado o copiado (el original no se modifica)
source/meta.json            metadatos de ffprobe y de yt-dlp
audio/audio16k.wav          audio normalizado mono 16 kHz
transcript/transcript.json  contrato `docs/architecture.md §6.1`
```

Las pruebas lentas (`pytest -m slow`) ejecutan `mlx-whisper` real con el modelo `tiny` y solo corren en
macOS arm64 con el modelo en caché de Hugging Face.

## Estructura

```
apps/api/            FastAPI + CLI (Python 3.12, uv)
apps/web/            Next.js 16 (App Router, Tailwind v4, shadcn/ui)
packages/api-client/ cliente TypeScript (se generará desde OpenAPI)
assets/fonts/        fuentes OFL con sus licencias
docs/architecture.md arquitectura y contratos entre changes
openspec/            especificaciones y changes (OpenSpec)
```

## Tests y lint

```bash
uv run --project apps/api pytest
uv run --project apps/api ruff check . && uv run --project apps/api ruff format --check .
pnpm --filter web lint && pnpm --filter web build
```

## Seguridad

El repositorio es público: `.env`, `client_secret*.json`, tokens, cookies, perfiles de navegador,
`storage/` y la media quedan fuera de git, y [gitleaks](https://github.com/gitleaks/gitleaks) los
escanea en pre-commit y en CI. Nunca se imprimen secretos en logs ni en el diagnóstico.

## Licencia

[AGPL-3.0](LICENSE). Las fuentes incluidas en `assets/fonts` tienen licencia SIL Open Font License y
cada familia conserva su `OFL.txt`. Las fuentes comerciales no se distribuyen: se cargan en local desde
`USER_FONTS_DIR`.
