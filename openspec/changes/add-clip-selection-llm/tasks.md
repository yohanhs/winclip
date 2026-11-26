# Tasks

## 1. Dependencias, configuración y contratos de reglas

- [ ] 1.1 Añadir `google-genai` y `openai` a `apps/api/pyproject.toml`, extender `apps/api/winclip/core/config.py` con las variables opcionales de modelos por defecto y timeouts (`GEMINI_MODEL`, `NVIDIA_MODEL`, `OPENROUTER_MODEL`, `GROQ_MODEL`, `OLLAMA_MODEL`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES_PER_PROVIDER`, `LLM_SCORE_THRESHOLD`, `LLM_SINGLE_PASS_MAX_CHARS`), actualizar `.env.example` y añadir helpers de rutas (`selection_path`, `llm_cache_path`) en `apps/api/winclip/core/storage.py`. Verificar con `uv sync --project apps/api` y tests de carga de configuración por defecto.
- [ ] 1.2 Implementar `apps/api/winclip/rules/schema.py` (`CampaignRules` con los 17 campos de `docs/architecture.md §6.4` y función `load_rules(path)`) y `apps/api/winclip/rules/validator.py` (validación de duración, `banned_words` case-insensitive por límite de palabra y `required_keywords`). Verificar con tests unitarios en `apps/api/tests/test_rules.py` cubriendo carga JSON válida/inválida y todos los casos de validación.

## 2. Gateway LLM (`llm-gateway`)

- [ ] 2.1 Implementar `apps/api/winclip/llm/types.py` (protocolo `LLMProvider` de `docs/architecture.md §8`, `ProviderAttempt`, `LLMResult`, excepciones tipadas `LLMError`, `RateLimitError`, `ProviderUnavailableError`, `InvalidJSONResponseError`) y `apps/api/winclip/llm/cache.py` (cálculo SHA-256 canónico sobre prompt + esquema + modelo lógico, lectura/escritura atómica en `storage/cache/llm/<sha256>.json`). Verificar con tests unitarios en `apps/api/tests/test_llm_cache.py` comprobando hits, misses por cambio de prompt/esquema y ausencia de secretos en disco.
- [ ] 2.2 Implementar los proveedores en `apps/api/winclip/llm/providers/` (`gemini.py` con `google-genai`, base común `openai_compat.py` con SDK `openai`, más `nvidia.py`, `openrouter.py`, `groq.py` y `ollama.py` con comprobación `available()` vía `/api/tags`). Verificar con tests unitarios en `apps/api/tests/test_llm_providers.py` mockeando las respuestas de ambos SDKs y validando `available()`, timeouts y mapeo de códigos HTTP 429/5xx/401.
- [ ] 2.3 Implementar `apps/api/winclip/llm/router.py` (`LLMRouter`: orden `LLM_PROVIDER_ORDER`, omisión de no disponibles, backoff exponencial con `sleep_fn` inyectable ante 429/5xx/timeout, bucle de autocorrección JSON con el error de Pydantic, integración de caché y estimación de tokens) y un `FakeLLMProvider` determinista en `apps/api/tests/fakes.py`. Verificar con tests en `apps/api/tests/test_llm_router.py` cubriendo fallback por ausencia de clave, 429 persistente, timeout, JSON malformado corregido en reintento, fallo total y caché.

## 3. Segmentación y selección de clips (`clip-selection`)

- [ ] 3.1 Crear los prompts versionados en `apps/api/winclip/llm/prompts/` (`select_single_v1.md`, `select_chunk_v1.md`, `select_rank_v1.md` y cargador con identificador de versión) e implementar `apps/api/winclip/pipeline/segment.py` (construcción de *utterances* por frases/pausas >= 0.7 s, serialización compacta, partición en chunks con solapamiento y algoritmo determinista de *snap* a límites exactos de palabra). Verificar con tests unitarios en `apps/api/tests/test_segment.py` cubriendo puntuación, pausas, chunks solapados y *snap* sin cortar palabras.
- [ ] 3.2 Implementar los modelos Pydantic de `candidates.json` (`docs/architecture.md §6.2`) y el selector completo en `apps/api/winclip/pipeline/select.py`: flujo en una pasada vs chunks + ranking global, inyección de reglas e idioma efectivo (`transcript.language` salvo regla explícita), post-validación (`banned_words`, `required_keywords`, duración), resolución de solapes, modo `--count N` y `--count max`, verificación de invariantes y escritura atómica de `selection/candidates.json`. Verificar con tests deterministas en `apps/api/tests/test_select.py` usando `FakeLLMProvider` para videos cortos, videos largos (> umbral de chunking), `--count max`, reglas, idiomas e invalidación de caché por versión de prompt.

## 4. Subcomandos CLI y documentación

- [ ] 4.1 Añadir el grupo `winclip llm test` y el comando `winclip select <project_id> --count N|max [--rules ruta.json] [--no-cache]` en `apps/api/winclip/cli.py`, con salida legible en Rich (tabla de intentos LLM y resumen de candidatos con score/duración/título) y códigos de salida no nulos ante errores. Verificar con tests de `CliRunner` en `apps/api/tests/test_cli_llm_select.py` usando `FakeLLMProvider`.
- [ ] 4.2 Actualizar `README.md` con las instrucciones de configuración de proveedores LLM gratuitos, el comando `winclip llm test`, el comando `winclip select` (incluyendo `--count max` y un ejemplo de `rules.json`) y la ubicación de caché y `candidates.json`. Verificar ejecutando `uv run --project apps/api winclip llm test --help && uv run --project apps/api winclip select --help` y contrastando las opciones documentadas.

## 5. Verificación integrada

- [ ] 5.1 Ejecutar `uv run --project apps/api ruff check . && uv run --project apps/api ruff format --check .`, `uv run --project apps/api pytest -m "not slow"`, probar el flujo encadenado `ingest` → `transcribe` (simulado) → `select` (con `FakeLLMProvider`) verificando todos los invariantes de `selection/candidates.json`, y ejecutar `openspec validate add-clip-selection-llm --strict` sin errores.

## Workflow follow-up

- Revisión del orquestador y prueba manual en local de `winclip llm test` y `winclip select` contra al menos un proveedor real configurado (Gemini/NVIDIA/Ollama).
- Archivar el change con `openspec archive add-clip-selection-llm` tras la aprobación.
