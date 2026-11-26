# Design

## Context

El repositorio está vacío, salvo `openspec/` y `docs/architecture.md`, que define estructura, variables de entorno y contratos. La máquina es un M1 con Node 24, pnpm, uv y Python 3.11/3.12/3.14/3.15. ffmpeg-full está instalado como keg-only en `/opt/homebrew/opt/ffmpeg-full/bin/`, mientras que el `ffmpeg` del PATH no tiene libass. Los modelos de Ollama viven en un disco externo que puede no estar montado.

## Goals / Non-Goals

**Goals:**
- Esqueleto que respete exactamente `docs/architecture.md §3–4`.
- Doctor fiable que sirva de puerta de entrada a todos los changes siguientes.
- Repo seguro para publicarse desde el primer commit.

**Non-Goals:**
- Modelos de dominio y migraciones (change `add-api-jobs`).
- Generación del cliente TS desde OpenAPI (se deja el paquete creado; se activa en `add-web-ui-cards`).

## Decisions

1. **Python 3.12 fijado con uv** (`.python-version` + `requires-python = ">=3.12,<3.13"`). mediapipe y opencv aún no tienen wheels estables para 3.14+. Alternativa descartada: 3.14, por falta de wheels.
2. **Typer + Rich para la CLI `winclip`**, como entry point en `pyproject.toml` (`[project.scripts] winclip = "winclip.cli:app"`). Da salida legible y es fácil de testear. Alternativa: argparse, más verboso.
3. **Checks del doctor como funciones puras** registradas en `winclip/core/doctor.py`: cada una devuelve `CheckResult(name, status, detail, hint)`. La CLI y `/api/health` reutilizan el mismo registro, con timeout de 3 s por check.
   - ffmpeg: ejecutar `FFMPEG_BIN -hide_banner -filters` y buscar ` ass ` y ` subtitles `.
   - whisper: comprobar la caché HF (`huggingface_hub.scan_cache_dir` o la ruta `models--mlx-community--whisper-large-v3-turbo`) **sin importar mlx** (se instala en el change 1).
   - ollama: `GET {OLLAMA_HOST}/api/tags` → `warn` si falla.
   - playwright: buscar Chromium en `~/Library/Caches/ms-playwright/chromium-*` → `warn` si falta.
   - claves: `present`/`absent` por nombre.
4. **`concurrently` en el package.json raíz**, con `--kill-others-on-fail` y prefijos `api`/`web`. El script de la API usa `uv run --project apps/api uvicorn winclip.main:app --reload --port 8000`. Alternativas: Procfile/honcho, que añade una dependencia Python innecesaria; turbo, excesivo por ahora.
5. **Next.js 15 App Router + Tailwind v4 + shadcn/ui + TanStack Query.** El fetch a la API va por `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). CORS en FastAPI solo para `http://localhost:3000`.
6. **Seguridad:** `pre-commit` (instalado con `uv tool install pre-commit`) con el hook oficial `gitleaks/gitleaks` y `ruff`. En CI se usa `gitleaks/gitleaks-action@v2`, más jobs `api` (uv sync, ruff, pytest) y `web` (pnpm install, lint, build).
7. **Fuentes OFL** descargadas de Google Fonts, cada familia con su `OFL.txt`: Montserrat, Poppins, Anton, Bebas Neue, League Spartan, Inter. Noto Color Emoji se deja para el change 3.

## Risks / Trade-offs

- [El disco externo no está montado y Ollama falla] → por diseño es solo `warn`.
- [Next 15 y Tailwind v4 introducen cambios frecuentes] → fijar versiones exactas en el lockfile.
- [gitleaks da falsos positivos con IDs de ejemplo en docs] → `.gitleaks.toml` con allowlist mínima y documentada.
