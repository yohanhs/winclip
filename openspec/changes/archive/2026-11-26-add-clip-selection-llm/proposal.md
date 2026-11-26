# Proposal

## Why

Con el video ingestado y transcrito en `add-ingest-transcription`, WinClip necesita una capa fiable para identificar automáticamente los mejores momentos de un video largo usando únicamente proveedores LLM gratuitos y tolerantes a cuotas (429). Separar un gateway LLM reutilizable de la lógica de selección de clips permite probar la calidad editorial de `candidates.json` desde la CLI antes de construir el render, la API y las campañas completas.

## What Changes

- Gateway LLM (`apps/api/winclip/llm/`) con enrutador de proveedores gratuitos en el orden `LLM_PROVIDER_ORDER` (`gemini -> nvidia -> openrouter -> groq -> ollama`), omisión de proveedores no disponibles o sin clave, backoff y fallback ante 429/5xx/timeouts, validación estricta de salida JSON con reintento de autocorrección, caché determinista en `storage/cache/llm/<sha256>.json` y trazabilidad de proveedor/modelo y tokens aproximados.
- Adaptadores para Gemini (SDK `google-genai`), NVIDIA NIM, OpenRouter, Groq y Ollama (vía endpoints compatibles con OpenAI `/v1`), con modelos por defecto configurables en `core/config.py` y comando de verificación `winclip llm test`.
- Esquema y validador de reglas (`apps/api/winclip/rules/schema.py` y `validator.py`) compatibles con `docs/architecture.md §6.4` para cargar un archivo `rules.json` opcional, inyectarlo en el prompt y validar post-LLM duración, `banned_words` y `required_keywords`.
- Pipeline de segmentación y selección (`apps/api/winclip/pipeline/segment.py` y `select.py`), prompts versionados en `apps/api/winclip/llm/prompts/` y comando CLI `winclip select <project_id> --count N|max [--rules rules.json]`:
  - Segmentación por frases y pausas respetando límites exactos de palabra.
  - Selección en una sola pasada cuando la transcripción cabe en contexto o en chunks con solapamiento + ranking global para videos largos.
  - Generación de `selection/candidates.json` exacto al contrato `docs/architecture.md §6.2` con sus invariantes y metadatos en el idioma del video salvo regla explícita.
- Suite de tests deterministas con proveedor LLM falso y actualización de `README.md` y `.env.example`.

**Fuera de alcance:** CRUD de campañas en base de datos y parser de reglas desde texto libre (llegan en `add-campaign-rules`), render de clips/subtítulos (`add-render-reframe-subtitles`), cola de jobs/endpoints HTTP (`add-api-jobs`), modelos de pago y streaming interactivo de respuestas LLM.

## Capabilities

### New Capabilities
- `llm-gateway`: enrutamiento resiliente entre proveedores LLM gratuitos con fallback ante errores/límites de tasa, validación estructurada de JSON con autocorrección, caché por hash en disco, trazabilidad de consumo y prueba de conectividad por CLI.
- `clip-selection`: segmentación de transcripciones alineada a palabras, selección y puntuación de clips (una pasada o por chunks con ranking global) con reglas opcionales y persistencia de `candidates.json` garantizando sus invariantes.

### Modified Capabilities

## Impact

- Código nuevo en `apps/api/winclip/llm/` (`router.py`, `cache.py`, `types.py`, `providers/{gemini,nvidia,openrouter,groq,ollama}.py`, `prompts/`), `apps/api/winclip/rules/` (`schema.py`, `validator.py`), `apps/api/winclip/pipeline/` (`segment.py`, `select.py`) y tests en `apps/api/tests/`.
- Código modificado: `apps/api/winclip/core/config.py` (modelos por defecto y timeouts opcionales), `apps/api/winclip/core/storage.py` (rutas de `selection/` y `cache/llm/`), `apps/api/winclip/cli.py` (`winclip llm test`, `winclip select`), `apps/api/pyproject.toml`, `.env.example` y `README.md`.
- Dependencias Python nuevas: `google-genai` y `openai`.
- Artefactos en disco bajo `STORAGE_DIR/cache/llm/` y `STORAGE_DIR/projects/<project_id>/selection/candidates.json` (ya excluidos de git).
