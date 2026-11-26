# Design

## Context

Ver `proposal.md` para la motivación. Este change depende de `add-clip-selection-llm` (router LLM + `pipeline/select.py`), `add-render-reframe-subtitles` (`pipeline/render.py` + presets de subtítulos), `add-api-jobs` (SQLModel, cola de jobs, routers REST) y `add-web-ui-cards` (UI de `/projects/new` y tarjetas de clips en `/projects/[id]`).

`docs/architecture.md` ya fija el esquema de campos de reglas (§6.4), la tabla `campaign` (§7), la ubicación de módulos (`winclip/rules/{schema,parser,validator}.py` y `winclip/routers/campaigns.py`, §3) y el campo `rule_violations` en `candidates.json` (§6.2).

## Goals / Non-Goals

**Goals:**
- Esquema Pydantic único (`CampaignRules`) que sirva tanto para validación API, parseo estructurado desde LLM, plantillas y consumo en el pipeline.
- Parseo de briefs en texto libre transparente para el usuario (distinguiendo explícitamente valores extraídos vs inferidos).
- Validación determinista reproducible de `rule_violations` independiente del LLM, para detectar incumplimientos incluso cuando el modelo ignora una restricción del prompt.
- Integración limpia en `select.py` y `render.py` manteniendo compatibilidad total con proyectos sin campaña (`campaign_id = null`).

**Non-Goals:**
- Re-entrenamiento o embeddings semánticos locales para validar `banned_topics` (la validación determinista cubre reglas léxicas/estructurales; las reglas semánticas se instruyen al LLM y se apoyan en su autoevaluación).
- Descarga automática de briefs desde fuentes externas o parseo de PDFs/DOCX.
- Editor gráfico interactivo de posición de marca de agua (se fija una posición segura estándar para 9:16).

## Decisions

1. **Un solo modelo Pydantic `CampaignRules` con validadores estrictos (`winclip/rules/schema.py`).**
   - Reglas de validación: `name` no vacío (1–120 chars), `language` en `Literal["es", "en", "auto"]` (default `"auto"`), `min_duration` en `[5, 179]`, `max_duration` en `[6, 180]` con `min_duration < max_duration`, `max_clips` en `[1, 50]` (default `10`), `hook_max_seconds` en `[1, 15]` y `<= min_duration` (default `3`), `target_platforms` subconjunto de `{"youtube", "tiktok", "instagram"}`, `hashtags` normalizados con prefijo `#` y deduplicados, `subtitle_preset` verificado contra `assets/subtitle-presets/*.json` si no es `None`, y `watermark_path` validado como ruta relativa dentro de `STORAGE_DIR/campaigns/` con extensión `.png` o `.webp`.
   - *Alternativa descartada:* JSON Schema separado en frontend y backend. Un único modelo Pydantic exportado a OpenAPI alimenta `packages/api-client` y evita divergencias.

2. **Parseo de briefs en dos pasos con marca de campos inferidos (`winclip/rules/parser.py`).**
   - El prompt del parser instruye al router LLM (`llm-gateway`) a devolver un esquema `ParsedCampaignDraft(rules: CampaignRules, inferred_fields: list[str], warnings: list[str])` donde el modelo lista explícitamente cada campo que no aparecía en el brief y completó con valores sugeridos.
   - Además, el parser ejecuta una verificación post-LLM: cualquier campo obligatorio con valor por defecto cuyo texto no tenga respaldo heurístico o que haya sido rellenado por fallback de validación se agrega a `inferred_fields`.
   - `POST /api/campaigns/parse` nunca escribe en SQLite; el cliente muestra los badges "Inferido" y solo persiste cuando el usuario pulsa "Guardar" (`POST /api/campaigns`).
   - *Alternativa descartada:* parseo por regex/reglas fijas. Los briefs de clipping varían mucho en redacción ES/EN; el router LLM gratuito ya cachea por hash de entrada y valida JSON con Pydantic.

3. **Validador determinista de incumplimientos (`winclip/rules/validator.py`).**
   - Se ejecuta sobre cada candidato devuelto por `pipeline/select.py` (y al revalidar metadatos editados de un clip):
     - `duration_out_of_range`: `end - start < min_duration` o `> max_duration`.
     - `banned_word_present`: coincidencia insensible a mayúsculas/acentos (límites de palabra) de `banned_words` en la transcripción del tramo, `title`, `hook` o `description`.
     - `missing_required_keyword`: ninguna aparición de una entrada de `required_keywords` en transcripción ni metadatos del clip.
     - `missing_required_hashtag`: hashtags definidos en la campaña ausentes en `candidate.hashtags`.
     - `hook_too_long`: si el hook textual estimado excede `hook_max_seconds` (heurística de palabras/segundo o duración del primer segmento).
   - También conserva cualquier incumplimiento semántico que el selector LLM reporte (p. ej. `banned_topic_risk`), normalizado al mismo formato `RuleViolation`.
   - *Alternativa descartada:* descartar silenciosamente clips con incumplimientos. En clipping conviene mostrar los candidatos con alertas claras para que el editor decida si ajusta el recorte/metadatos o descarta la tarjeta.

4. **Gestión segura de marca de agua (`watermark_path`).**
   - Se expone `POST /api/campaigns/watermarks` (multipart PNG/WebP, tamaño máx. 5 MB) que guarda el archivo en `storage/campaigns/watermarks/<ulid>.<ext>` y devuelve la ruta relativa `campaigns/watermarks/<ulid>.<ext>`.
   - `render.py` resuelve la ruta vía `Storage.path(...)`, rechaza cualquier `..` o ruta absoluta fuera de `STORAGE_DIR`, y aplica un overlay escalado (~14% del ancho de 1080px, opacidad 0.85) en esquina superior derecha con margen seguro (`x=W-w-48:y=140`) para no solaparse con subtítulos (`y=0.66*H`) ni controles de Shorts/Reels/TikTok.
   - *Alternativa descartada:* aceptar rutas absolutas arbitrarias del sistema de archivos desde la API, por riesgo de path traversal y lectura indebida de archivos locales.

5. **Aplicación de `cta_text` y `hook_max_seconds` en `render.py`.**
   - Si `campaign.subtitle_preset` está definido y el clip no especifica un override explícito, `render.py` adopta el preset de la campaña.
   - `hook_max_seconds` acota la duración del overlay inicial de hook en el clip renderizado (`min(default_hook_duration, campaign.hook_max_seconds)`).
   - `cta_text` se renderiza como banner discreto en los últimos 3 segundos del clip (por encima de la zona de subtítulos para evitar colisión) y se añade como sugerencia al final de la descripción generada del clip.

6. **Plantillas ES/EN versionadas como JSON estático en `assets/campaign-templates/`.**
   - Se incluyen 4 plantillas listas para usar (2 en español, 2 en inglés): podcast/entrevistas ES, finanzas/educativo ES, creator clipping bounty EN y SaaS/tech demo clipping EN.
   - Servidas vía `GET /api/campaigns/templates` (validando al cargar que cumplan `CampaignRules`).
   - *Alternativa descartada:* seed mutable en SQLite, que se desincroniza o ensucia la lista de campañas del usuario desde el primer arranque.

7. **Dependencias nuevas.**
   - No se requieren nuevas dependencias Python ni JS. Se reutiliza el stack existente (`pydantic`, `sqlmodel`, `fastapi`, `llm-gateway`, `ffmpeg-full`, `shadcn/ui`, `@tanstack/react-query`, `packages/api-client`).

## Contratos

Contratos nuevos que complementan `docs/architecture.md §6.4` y `§7` sin contradecirlos:

- **Tabla `campaign` (extensión compatible con §7):**
  `id (ULID), workspace_id, name, rules_json (TEXT/JSON de CampaignRules), source_text (TEXT nullable), created_at, updated_at`. En `project.campaign_id`, FK nullable con `ON DELETE SET NULL`.
- **Formato de `RuleViolation` dentro de `candidates.json` (`rule_violations[]`) y `clip`:**
  ```json
  {
    "code": "banned_word_present | duration_out_of_range | missing_required_keyword | missing_required_hashtag | hook_too_long | banned_topic_risk",
    "field": "banned_words",
    "severity": "warning | error",
    "message": "Contiene la palabra prohibida 'garantizado' en el título"
  }
  ```
- **Endpoints `/api/campaigns`:**
  - `GET /api/campaigns` → lista de campañas del workspace.
  - `GET /api/campaigns/templates` → lista de plantillas predefinidas ES/EN (`{id, title, description, language, rules}`).
  - `POST /api/campaigns` → crea campaña `{name, rules, source_text?}` → `201`.
  - `GET /api/campaigns/{id}` → detalle de campaña.
  - `PATCH /api/campaigns/{id}` → actualiza parcialmente `name`, `rules` y/o `source_text`.
  - `DELETE /api/campaigns/{id}` → elimina campaña (`204`), dejando `project.campaign_id = null`.
  - `POST /api/campaigns/{id}/duplicate` → clona la campaña con nuevo ULID y nombre `<name> (copia)` → `201`.
  - `POST /api/campaigns/parse` → recibe `{source_text: str}` → devuelve `{rules: CampaignRules, inferred_fields: list[str], warnings: list[str], provider: str}`.
  - `POST /api/campaigns/watermarks` → sube imagen PNG/WebP → devuelve `{watermark_path: str}`.

## Risks / Trade-offs

- [Un LLM gratuito/pequeño omite marcar algún campo en `inferred_fields` o devuelve valores fuera de rango] → Post-procesado en `parser.py` que valida contra `CampaignRules`, corrige o registra `warnings`, y exige confirmación explícita del usuario en la UI antes de guardar.
- [Validación estricta de `banned_words` produce falsos positivos con subcadenas] → Coincidencia por límites de palabra normalizada (minúsculas y sin tildes) y presentación como alerta visible no bloqueante en la tarjeta del clip.
- [El overlay de `cta_text` o `watermark_path` solapa subtítulos en 9:16] → Zonas seguras fijas en `render.py` (watermark arriba derecha `y=140`, subtítulos `y=0.66*H`, CTA en franja reservada los últimos 3 s) cubiertas por tests de construcción del grafo de filtros FFmpeg.
- [Cambio de reglas en una campaña ya usada por proyectos anteriores] → Los proyectos nuevos toman las reglas vigentes; los clips ya renderizados conservan su `candidates.json` y `render.json` sin alterarse retroactivamente.
