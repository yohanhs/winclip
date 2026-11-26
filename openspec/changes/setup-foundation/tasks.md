# Tasks

## 1. Raíz del monorepo y seguridad

- [x] 1.1 Crear `.gitignore` (Node, Python, `.env*` excepto `.env.example`, `client_secret*.json`, `**/tokens/`, `storage/`, `*.mp4|*.mov|*.wav|*.mp3|*.mkv|*.webm`, perfiles de Playwright, `.DS_Store`) y `.editorconfig`. Verificar: crear `apps/api/.env` y `client_secret_x.json` de prueba y comprobar que `git status --porcelain` no los lista; luego borrarlos.
- [x] 1.2 Añadir `LICENSE` (texto oficial AGPL-3.0) y un `README.md` inicial (qué es, requisitos, `pnpm dev`, `winclip doctor`, enlace a `docs/architecture.md`). Verificar que ambos archivos existen y que el README menciona AGPL-3.0.
- [x] 1.3 Crear `pnpm-workspace.yaml` (apps/*, packages/*) y un `package.json` raíz con los scripts `dev` (concurrently con `--kill-others-on-fail`, prefijos api/web), `lint` y `test`. Verificar con `pnpm install`, que debe terminar sin errores.
- [x] 1.4 Configurar `.pre-commit-config.yaml` con gitleaks y ruff, más `.gitleaks.toml`. Verificar: `pre-commit run --all-files` pasa, y un archivo temporal con `AIzaSy` + 33 caracteres falsos hace fallar `pre-commit run gitleaks --files <archivo>`.

## 2. Backend base (apps/api)

- [x] 2.1 `uv init` del paquete `winclip` con Python 3.12 (`.python-version`), dependencias fastapi, uvicorn[standard], pydantic-settings, typer, rich, httpx, huggingface_hub; dev: ruff, pytest, pytest-asyncio. Verificar que `uv run python -c "import winclip"` funciona.
- [x] 2.2 Implementar `winclip/core/config.py` (Settings con todas las variables de `docs/architecture.md §4`, derivando `DATABASE_URL` de `STORAGE_DIR` cuando no se indique) y `.env.example` en la raíz con comentarios (incluyendo ejemplo de volumen externo para `STORAGE_DIR`). Verificar con un test que los defaults cargan sin `.env`, que `DATABASE_URL` sigue a `STORAGE_DIR`, y que `FFMPEG_BIN` se puede sobrescribir por entorno.
- [x] 2.3 Implementar `winclip/core/doctor.py` con los checks: ffmpeg (filtros ass y subtitles), ffprobe, yt-dlp, modelo whisper en caché, ollama (warn), playwright chromium (warn), volumen `/Volumes/yohan` (warn), `STORAGE_DIR` montado y escribible (error si apunta a un `/Volumes/<vol>` no montado sin crear carpetas ahí) y claves LLM (present/absent). Verificar con tests parametrizados que usen binarios falsos (scripts temporales) para los casos ok, error y warn, y con un test que asegure que ningún valor de clave aparece en la salida.
- [x] 2.4 Crear `winclip/cli.py` (Typer) con `winclip doctor` (tabla Rich, exit code 1 si hay algún `error`) y registrar `[project.scripts]`. Verificar que `uv run winclip doctor` en esta máquina sale con código 0.
- [x] 2.5 Crear `winclip/main.py` (FastAPI, CORS para localhost:3000) y `routers/health.py` con `GET /api/health` → `{app, version, checks[]}`. Verificar con un test de TestClient que devuelve 200 y la lista de checks.

## 3. Frontend base (apps/web)

- [x] 3.1 Crear la app Next.js 15 (TypeScript strict, App Router, Tailwind v4, ESLint) en `apps/web`, inicializar shadcn/ui y añadir @tanstack/react-query con un provider. Verificar que `pnpm --filter web build` termina sin errores.
- [x] 3.2 Construir el layout con sidebar (Proyectos, Campañas, Cuentas, Publicaciones, Ajustes) y páginas placeholder, usando `APP_NAME` desde `NEXT_PUBLIC_APP_NAME`. Verificar navegando las 5 rutas con `pnpm --filter web dev`.
- [x] 3.3 Crear la página `/settings/status` que consume `GET /api/health`: badge por check, detalle y hint, más el aviso "API no disponible" con el comando para arrancarla. Verificar manualmente con la API arriba y abajo y dejar captura en la PR.
- [x] 3.4 Crear `packages/api-client` con un `package.json` y README que explique que se generará desde OpenAPI en el change 5. Verificar que `pnpm install` lo reconoce como workspace.
- [x] 3.5 Actualizar `apps/web` a la última versión estable de Next.js 16 (`next`, `eslint-config-next`) y Tailwind v4 estable, fijar `engines.node` a `>=24.0.0`, `.nvmrc` a `24` y `node-version: 24` en `.github/workflows/ci.yml`, acotar `dev:api` con `--reload-dir apps/api`, configurar `asyncio_default_fixture_loop_scope = "function"` en `apps/api/pyproject.toml` y actualizar `README.md` a Next.js 16 y Node 24. Verificar que `pnpm lint`, `pnpm test`, `pnpm --filter web build` y `pre-commit run --all-files` pasan sin errores ni warnings de pytest-asyncio.

## 4. Assets y CI

- [x] 4.1 Descargar las fuentes OFL (Montserrat, Poppins, Anton, Bebas Neue, League Spartan, Inter) en `assets/fonts/<familia>/` con su `OFL.txt`. Verificar que cada carpeta tiene su licencia.
- [x] 4.2 Crear `.github/workflows/ci.yml` con los jobs gitleaks, api (uv sync, ruff check, ruff format --check, pytest) y web (pnpm install --frozen-lockfile, lint, build). Verificar la sintaxis con `actionlint` si está disponible, o revisión manual.

## 5. Verificación integrada

- [x] 5.1 Ejecutar `pnpm dev` y comprobar que API (8000) y web (3000) responden y que `/settings/status` muestra los checks en verde (warn aceptable en Ollama y Playwright). Ejecutar `openspec validate setup-foundation --strict` sin errores.

## Workflow follow-up

- Revisión del orquestador y del usuario; commit inicial en `main`.
- Crear el repo público `yohanhs/winclip` solo con confirmación explícita del usuario.
- Archivar el change con `openspec archive setup-foundation`.
