# Proposal

## Why

WinClip arranca desde un directorio vacío. Antes de construir el pipeline de clipping hace falta una base común: monorepo, entornos reproducibles (uv y pnpm), un comando que levante todo y un diagnóstico (`doctor`) que confirme que las herramientas locales críticas están disponibles. Como el repo será público desde el día uno, la protección contra fugas de secretos también tiene que existir antes del primer commit con código.

## What Changes

- Monorepo pnpm con `apps/web` (Next.js 15), `apps/api` (FastAPI, Python 3.12 con uv) y `packages/api-client` (vacío por ahora, preparado para generación OpenAPI).
- Configuración central del backend (`.env` → Settings) con las variables de `docs/architecture.md §4` y un `.env.example` documentado.
- Endpoint `GET /api/health` y comando CLI `winclip doctor`, que verifican: ffmpeg-full con libass, ffprobe, yt-dlp, modelo whisper en caché, Ollama accesible, presencia (sin revelar valor) de las claves LLM, Chromium de Playwright, disco `/Volumes/yohan` montado (aviso, no error) y directorio de almacenamiento escribible.
- Página web "Estado del sistema" que muestra el resultado del doctor, más el layout base con navegación (Proyectos, Campañas, Cuentas, Publicaciones, Ajustes) con páginas placeholder.
- `pnpm dev` levanta la API (8000) y la web (3000) a la vez.
- Seguridad del repo público: `.gitignore` estricto, gitleaks en pre-commit y en GitHub Actions, CI con lint y tests de ambas apps.
- Licencia AGPL-3.0, README inicial y fuentes OFL en `assets/fonts` con sus licencias.

**Fuera de alcance:** cualquier lógica del pipeline (ingesta, transcripción, LLM, render), base de datos de dominio, autenticación de usuarios, publicación del repo en GitHub (lo hace el usuario o se confirma aparte).

## Capabilities

### New Capabilities
- `dev-environment`: arranque local del sistema, configuración centralizada y diagnóstico de dependencias (doctor CLI + endpoint + página de estado).
- `repo-security`: garantías de que el repositorio público no contiene secretos ni datos del usuario.

### Modified Capabilities

## Impact

- Código nuevo: `apps/api`, `apps/web`, `packages/api-client`, `scripts/`, `.github/workflows/ci.yml`, `assets/fonts`.
- Dependencias Python: fastapi, uvicorn[standard], pydantic-settings, typer, rich, httpx; desarrollo: ruff, pytest, pytest-asyncio.
- Dependencias JS: next@15, react, tailwindcss v4, shadcn/ui, @tanstack/react-query, concurrently.
- Herramientas: pre-commit, gitleaks.
