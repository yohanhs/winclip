# AGENTS.md: guía para agentes implementadores

Implementas WinClip siguiendo **OpenSpec**. El orquestador (planificador) es quien crea y mantiene los changes. Tú solo los implementas.

## Antes de empezar
1. Lee `openspec/config.yaml` (contexto, stack y reglas, de cumplimiento obligatorio) y `docs/architecture.md` (contratos compartidos).
2. Trabaja **un change a la vez**, en el orden de `docs/architecture.md §2`. No empieces un change si los que necesita no están archivados.
3. Crea una rama `change/<nombre>` desde `main`.

## Flujo por change
```bash
openspec list                                   # changes activos
openspec instructions apply --change <nombre> --json
# implementar las tareas en orden y marcar - [x] en tasks.md al completar cada una
openspec validate <nombre> --strict
```
- Usa el workflow `/opsx-apply <nombre>` (Antigravity/OpenCode) o `/opsx:apply <nombre>` (Claude Code/Gemini CLI).
- Marca una tarea como hecha solo cuando su verificación pase.
- **No archives.** El archivado (`openspec archive`) lo hace el orquestador después de revisar.

## Reglas inquebrantables
- No cambies el stack, las rutas de herramientas (`FFMPEG_BIN` = ffmpeg-full) ni los contratos de `docs/architecture.md` sin pedirlo antes al orquestador.
- Repo **público**: nunca commitees `.env`, tokens, `client_secret*.json`, cookies, perfiles de navegador, `storage/` ni media. El hook gitleaks debe pasar.
- Nunca imprimas secretos en logs, tests ni salidas del doctor.
- Si una tarea necesita una clave, un login (OAuth o Playwright) o una acción del usuario, **detente y pídela**. No la inventes ni la simules en código productivo.
- Si descubres que la spec o el design están mal o incompletos, **pausa y repórtalo** con una propuesta. No amplíes ni recortes el alcance por tu cuenta.
- El material previo del usuario en `/Volumes/yohan/...` (Canales de YouTube, Youtube API, etc.) es solo de lectura y referencia. La única ruta escribible ahí es `STORAGE_DIR` (`/Volumes/yohan/Proyectos/winclip/storage`), configurada en `.env` local.

## Comandos útiles
| Acción | Comando |
|---|---|
| Levantar todo | `pnpm dev` |
| Diagnóstico | `uv run --project apps/api winclip doctor` |
| Tests API | `uv run --project apps/api pytest` (los lentos van con `-m slow`) |
| Lint API | `uv run --project apps/api ruff check . && uv run --project apps/api ruff format --check .` |
| Web | `pnpm --filter web lint && pnpm --filter web build` |

## Al terminar un change, entrega
- Resumen de lo hecho, las tareas `N/N` y la salida de `openspec validate --strict`.
- Las desviaciones respecto al design, si las hubo, con su justificación.
- Pendientes o riesgos para el orquestador.
