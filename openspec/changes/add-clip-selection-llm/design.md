# Design

## Context

Véase `proposal.md` para la motivación. Este change depende de `add-ingest-transcription` (lee `transcript/transcript.json` y `source/meta.json` vía `LocalStorage` y genera IDs vía `core/ids.py`) y de `setup-foundation` (que ya expone `GEMINI_API_KEY`, `NVIDIA_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `LLM_PROVIDER_ORDER` y `OLLAMA_HOST` en `core/config.py`).

Todas las llamadas LLM deben usar exclusivamente tiers gratuitos de API o Ollama local como respaldo offline, tolerando límites de cuota (429), latencias variables y respuestas JSON imperfectas. La gestión completa de campañas en SQLite y el parser de texto libre de reglas llegarán en `add-campaign-rules` (change 6), por lo que este change implementa el esquema compartido `rules/schema.py` y el validador `rules/validator.py` cargando `rules.json` desde disco.

## Goals / Non-Goals

**Goals:**
- Implementar `LLMProvider` (`docs/architecture.md §8`) y un router resiliente con caché en disco reutilizable por `clip-selection` y por changes futuros (p. ej. parser de reglas en change 6).
- Implementar la selección de clips end-to-end vía CLI (`winclip select`) produciendo `candidates.json` exacto al contrato `docs/architecture.md §6.2` con invariantes verificados determinísticamente en código.
- Garantizar tests rápidos y 100% deterministas mediante un proveedor LLM falso, sin dependencias de red ni claves reales en CI.

**Non-Goals:**
- CRUD de campañas en base de datos ni conversión de texto libre a reglas (`add-campaign-rules`).
- Render de clips verticales o subtítulos (`add-render-reframe-subtitles`).
- Endpoints REST, cola de jobs o eventos SSE (`add-api-jobs`).

## Contratos

Contratos nuevos o ampliaciones compatibles introducidas por este change (sin modificar `docs/architecture.md`):

### 1. Variables de configuración opcionales en `core/config.py`
Todas tienen valores por defecto seguros para mantener arranque sin `.env`:
- `GEMINI_MODEL` = `"gemini-2.5-flash"`
- `NVIDIA_MODEL` = `"meta/llama-3.3-70b-instruct"`
- `OPENROUTER_MODEL` = `"meta-llama/llama-3.3-70b-instruct:free"`
- `GROQ_MODEL` = `"llama-3.3-70b-versatile"`
- `OLLAMA_MODEL` = `"qwen3.5:4b"`
- `LLM_TIMEOUT_SECONDS` = `60`
- `LLM_MAX_RETRIES_PER_PROVIDER` = `2`
- `LLM_SCORE_THRESHOLD` = `60` (umbral mínimo de `score` para `--count max`)
- `LLM_SINGLE_PASS_MAX_CHARS` = `45000`

### 2. Interfaz de proveedores y resultado del router (`winclip/llm/types.py`)
Los proveedores implementan `LLMProvider` de `docs/architecture.md §8` (`name: str`, `available() -> bool`, `complete_json(system, user, schema) -> BaseModel`) y exponen el atributo `model: str`. El router devuelve un envoltorio tipado:
```python
class ProviderAttempt(BaseModel):
    provider: str
    model: str
    status: Literal["ok", "skipped", "error"]
    error: str | None = None
    latency_ms: int = 0

class LLMResult(BaseModel, Generic[T]):
    data: T
    provider: str
    model: str
    cached: bool
    prompt_tokens: int
    completion_tokens: int
    attempts: list[ProviderAttempt]
```
El identificador compuesto para `candidates.json.provider` es `f"{result.provider}:{result.model}"`.

### 3. Entrada de caché en `storage/cache/llm/<sha256>.json`
- Clave: `sha256` del JSON canónico (`sort_keys=True, ensure_ascii=False`) de `{"logical_model": str, "system": str, "user": str, "schema": schema.model_json_schema()}` (donde `logical_model` incluye la versión del prompt, p. ej. `"clip-selection:single:v1"`).
- Contenido en disco:
```json
{
  "cache_key": "<sha256>",
  "logical_model": "clip-selection:single:v1",
  "provider": "gemini",
  "model": "gemini-2.5-flash",
  "created_at": "2026-11-26T15:30:00Z",
  "prompt_tokens": 1820,
  "completion_tokens": 410,
  "data": {}
}
```

### 4. `selection/candidates.json` (`docs/architecture.md §6.2`)
Modelo Pydantic exacto al contrato §6.2:
- `project_id: str`, `campaign_id: str | None = None`, `requested: int | Literal["max"]`, `provider: str`, `candidates: list[ClipCandidate]`.
- `ClipCandidate`: `id` (ULID minúsculas), `start`, `end`, `title`, `hook`, `description`, `hashtags`, `score` (`0..100`), `reason`, `language`, `rule_violations: list[RuleViolation]`, donde `RuleViolation` es `{"code": str, "field": str, "severity": Literal["warning", "error"], "message": str}` (compatible desde el inicio con `add-campaign-rules`).
- Nota: `requested` acepta el entero `N` (como en el ejemplo de §6.2) o el literal `"max"` cuando se invoca `--count max`.

### 5. `rules/schema.py` (`docs/architecture.md §6.4`)
Modelo Pydantic `CampaignRules` con los 17 campos de §6.4 y defaults seguros: `name="default"`, `language="auto"`, `min_duration=20`, `max_duration=60`, `max_clips=None`, `priority_topics=[]`, `banned_topics=[]`, `banned_words=[]`, `required_keywords=[]`, `tone=None`, `hook_max_seconds=3`, `cta_text=None`, `hashtags=[]`, `subtitle_preset=None`, `watermark_path=None`, `target_platforms=[]`, `extra_instructions=None`. Validaciones: `min_duration >= 5`, `max_duration > min_duration`, `max_clips is None or max_clips >= 1`.

## Decisions

1. **Dos SDKs mínimos para cinco proveedores (`google-genai` y `openai`).**
   - *Decisión:* `GeminiProvider` usa `google-genai` con `response_mime_type="application/json"` y `response_schema`. `NvidiaProvider`, `OpenRouterProvider`, `GroqProvider` y `OllamaProvider` heredan de una base común `OpenAICompatibleProvider` sobre el SDK oficial `openai` cambiando únicamente `base_url`, `api_key`, `model` y headers opcionales:
     - NVIDIA NIM: `https://integrate.api.nvidia.com/v1`
     - OpenRouter: `https://openrouter.ai/api/v1`
     - Groq: `https://api.groq.com/openai/v1`
     - Ollama: `{OLLAMA_HOST.rstrip('/')}/v1` (clave dummy `"ollama"`, disponibilidad verificada con `GET {OLLAMA_HOST}/api/tags` y timeout de 2 s cacheado en la instancia).
   - *Justificación de dependencias nuevas:* `google-genai` es el SDK oficial actual de Google AI Studio (reemplaza al deprecado `google-generativeai`); `openai` unifica 4 proveedores OpenAI-compatible con soporte nativo de timeouts, parsing de errores HTTP y conteo de `usage`.
   - *Alternativas:* escribir clientes manuales con `httpx` para cada proveedor (duplicaría manejo de reintentos, errores y formatos JSON); usar `litellm` (dependencia muy pesada y con alta superficie de fallos indirectos).

2. **Política de reintentos, corrección de JSON y fallback en `LLMRouter`.**
   - *Decisión:*
     - Proveedor con `available() == False` → registrar `Attempt(status="skipped")` y pasar al siguiente.
     - Error transitorio (HTTP 429, 5xx, timeout, error de conexión) → hasta `LLM_MAX_RETRIES_PER_PROVIDER` reintentos con backoff exponencial acotado (`min(1.0 * 2**attempt, 8.0)` + jitter, inyectable `sleep_fn` para tests instantáneos); si persiste, pasar al siguiente proveedor.
     - Error no transitorio de proveedor (401, 403, 404 de modelo) → sin reintentos, saltar inmediatamente al siguiente proveedor.
     - Error de parseo JSON o `ValidationError` de Pydantic → hasta 2 reintentos de autocorrección en el mismo proveedor añadiendo un bloque con el error concreto de validación y recordando responder exclusivamente JSON válido según el esquema; si persiste, pasar al siguiente proveedor.
     - Uso de tokens: leer `usage` del SDK cuando esté disponible y caer en estimación `max(1, len(text) // 4)` cuando el proveedor no lo reporte (sin añadir `tiktoken`).
   - *Alternativas:* fallar al primer 429 sin backoff (desperdicia Gemini cuando hay picos breves de cuota); omitir autocorrección JSON (degrada mucho modelos pequeños de Ollama o NIM).

3. **Caché por modelo lógico y versión de prompt.**
   - *Decisión:* la clave SHA-256 usa `(logical_model, system, user, json_schema)` y **no** el nombre del proveedor físico. Como `logical_model` incorpora la versión del prompt (p. ej. `clip-selection:single:v1`), la caché se reutiliza aunque cambie el orden de fallback y se invalida automáticamente al cambiar el prompt, su versión o el esquema Pydantic. Las lecturas/escrituras usan `LocalStorage.write_json_atomic` y nunca persisten claves de API.
   - *Alternativas:* incluir el proveedor físico en el hash (rompería la caché si Gemini devuelve 429 un día y NIM responde).

4. **Segmentación por frases y pausas (`pipeline/segment.py`) + snap determinista a palabras.**
   - *Decisión:* aplanar `transcript.segments[].words` en una lista indexada de palabras y construir *utterances* agrupando palabras hasta encontrar puntuación terminal (`.`, `?`, `!`) o una pausa inter-palabra `>= 0.7 s` (con tope de ~25 palabras por utterance para no crear bloques gigantes si falta puntuación). Cada utterance se serializa de forma compacta al LLM: `[U0012 04:12.3-04:18.9] Texto de la frase...`.
   - El esquema de salida del LLM acepta `start` y `end` en segundos (o índices de utterance) y `select.py` ejecuta un algoritmo de *snap* determinista a límites exactos de palabra: ajusta `start` al inicio de la palabra más cercana y `end` al fin de la palabra más cercana; si el redondeo empuja la duración ligeramente fuera de `[min_duration, max_duration]`, prueba expandir o contraer en una o más palabras vecinas dentro de un margen de ±3 s antes de descartar.
   - *Alternativas:* enviar el array completo de `words` al LLM (consume demasiados tokens en videos de 1 h y aumenta errores de timestamps inventados).

5. **Estrategia una pasada vs chunks con solapamiento + ranking global (`pipeline/select.py`).**
   - *Decisión:* si el texto serializado de utterances tiene `<= LLM_SINGLE_PASS_MAX_CHARS` (~45 000 caracteres), se ejecuta una única pasada con `select_single_v1.md`. Si excede el límite, se parte en chunks de ~35 000 caracteres con 15% de solapamiento alineado a límites de utterance; cada chunk usa `select_chunk_v1.md` y devuelve candidatos locales; finalmente se deduplican propuestas con solape `>= 50%` (conservando la de mayor score) y se ejecuta una pasada de ranking global (`select_rank_v1.md`) sobre el conjunto consolidado de candidatos antes de aplicar el post-procesado determinista.
   - *Alternativas:* cortar por duración fija en minutos sin solapamiento (rompe clips valiosos que cruzan la frontera entre bloques).

6. **Post-validación de reglas e invariantes (`rules/validator.py` + `pipeline/select.py`).**
   - *Decisión:* orden estricto de post-procesado tras recibir propuestas del LLM:
     1. Snap determinista a límites exactos de palabra de `transcript.json`.
     2. Filtro duro de duración: descartar si `end - start < rules.min_duration` o `> rules.max_duration`.
     3. Validación de `banned_words` (coincidencia insensible a mayúsculas con límites de palabra sobre el texto transcrito del clip + `title` + `hook` + `description`): si hay coincidencia, descartar el candidato.
     4. Validación de `required_keywords` (si la lista no está vacía y ninguna palabra clave aparece en el texto del clip o metadatos): añadir `RuleViolation(code="missing_required_keyword", field="required_keywords", severity="warning", message=...)` a `rule_violations`.
     5. En modo `--count max`: filtrar a candidatos con `score >= LLM_SCORE_THRESHOLD` y `rule_violations == []`, aplicando `rules.max_clips` como tope si está definido.
     6. En modo `--count N`: priorizar candidatos con `rule_violations == []` ordenados por `score` descendente (resolución codiciosa sin solapes), y recortar a `N` (o `min(N, rules.max_clips)` si `rules.max_clips` está definido); el resultado final se ordena por `score` descendente.
     7. Verificación final de invariantes (sin solapes, duración válida, alineación a palabras, orden descendente por `score`) antes de escribir `selection/candidates.json` de forma atómica.

7. **Prompts versionados en `apps/api/winclip/llm/prompts/`.**
   - *Decisión:* guardar `select_single_v1.md`, `select_chunk_v1.md` y `select_rank_v1.md` como archivos de texto dentro del paquete Python con una función cargadora que lee el archivo y devuelve `(version, template)`. Incluir en `pyproject.toml` los archivos `.md` como package data si fuera necesario.

## Risks / Trade-offs

- [Los modelos gratuitos de NVIDIA NIM, OpenRouter o Groq cambian de identificador o quedan temporalmente saturados] → todos los modelos son configurables vía `.env` sin tocar código y el router hace fallback automático entre proveedores.
- [Modelos locales pequeños (Ollama 3B–4B) producen menor calidad editorial o más JSON inválidos] → el bucle de autocorrección JSON más los invariantes deterministas en Python aseguran que `candidates.json` siempre sea estructuralmente válido, aunque Ollama se mantiene como último respaldo offline.
- [Videos muy largos (>2 h) pueden generar muchos candidatos intermedios antes del ranking global] → acotar los candidatos por chunk (ej. máx 10 por chunk) y pre-deduplicar por solape antes de invocar `select_rank_v1.md` para mantener el prompt final compacto.
- [El contrato `docs/architecture.md §6.2` muestra `"requested": 10` como entero, mientras el CLI admite `--count max`] → aceptar `int | Literal["max"]` en `candidates.json` preserva compatibilidad exacta con peticiones numéricas y documenta de forma explícita las peticiones exhaustivas.
