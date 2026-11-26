# Tasks

## 1. Esquema, validación y plantillas de campaña

- [ ] 1.1 Implementar `winclip/rules/schema.py` con `CampaignRules` (todos los campos de `docs/architecture.md §6.4`), `RuleViolation` y validadores (`5 <= min_duration < max_duration <= 180`, `max_clips`, `hook_max_seconds <= min_duration`, normalización de hashtags, validación de `subtitle_preset` y seguridad de `watermark_path`). Verificar con `uv run --project apps/api pytest tests/test_campaign_schema.py` cubriendo casos válidos, límites y rechazos.
- [ ] 1.2 Crear las plantillas de ejemplo ES/EN en `assets/campaign-templates/` (al menos 2 en español y 2 en inglés inspiradas en clipping campaigns) y un cargador validado contra `CampaignRules`. Verificar con tests en `tests/test_campaign_schema.py` que todas las plantillas cargan y pasan validación estricta.
- [ ] 1.3 Implementar `winclip/rules/validator.py` para evaluar candidatos/clips contra una `CampaignRules` y emitir `list[RuleViolation]` (duración, palabras prohibidas con normalización de acentos y límites de palabra, palabras clave obligatorias, hashtags faltantes, duración de hook). Verificar con `uv run --project apps/api pytest tests/test_campaign_validator.py`.

## 2. Parseo de briefs vía LLM y persistencia/API

- [ ] 2.1 Implementar `winclip/rules/parser.py` y su prompt en `winclip/llm/prompts/` usando `llm-gateway` para transformar un brief en texto libre ES/EN en `ParsedCampaignDraft` (`rules`, `inferred_fields`, `warnings`, `provider`), sin persistir y con post-verificación de campos inferidos. Verificar con tests con proveedor LLM simulado en `tests/test_campaign_parser.py` (brief completo, brief parcial y fallo de proveedores).
- [ ] 2.2 Añadir/actualizar el modelo SQLModel `Campaign` en `winclip/core/models.py` (con `ON DELETE SET NULL` en `project.campaign_id`) y asegurar la inicialización/migración limpia en SQLite. Verificar con tests de persistencia y borrado con proyectos asociados en `tests/test_campaigns_api.py`.
- [ ] 2.3 Implementar `winclip/routers/campaigns.py` con CRUD completo (`/api/campaigns`), `POST /api/campaigns/{id}/duplicate`, `GET /api/campaigns/templates`, `POST /api/campaigns/parse` y `POST /api/campaigns/watermarks` (validando MIME/tamaño y guardando bajo `storage/campaigns/watermarks/`), y registrarlo en `winclip/main.py`. Verificar con `uv run --project apps/api pytest tests/test_campaigns_api.py` (CRUD, duplicado, validación 422, parseo, watermark y protección contra path traversal).

## 3. Integración con selección y renderizado

- [ ] 3.1 Integrar `CampaignRules` en `winclip/pipeline/select.py` y `worker/handlers.py`: inyectar todas las reglas activas en el prompt de selección, aplicar el validador determinista para poblar `rule_violations` en `candidates.json` y persistirlas en la tabla `clip`. Verificar con tests en `tests/test_select_with_campaign.py` comparando ejecución con y sin campaña.
- [ ] 3.2 Integrar `CampaignRules` en `winclip/pipeline/render.py`: aplicar `subtitle_preset` de la campaña por defecto, limitar el hook overlay a `hook_max_seconds`, añadir overlay de `watermark_path` en zona segura y renderizar `cta_text` en los últimos segundos, actualizando `render.json`. Verificar con tests unitarios del comando/filtros FFmpeg en `tests/test_render_with_campaign.py` y un render real sobre clip de prueba.
- [ ] 3.3 Documentar el flujo de campañas, plantillas y `POST /api/campaigns/parse` en `README.md` y regenerar `packages/api-client` desde el esquema OpenAPI actualizado. Verificar que el cliente generado compila sin errores y que los comandos documentados en el README coinciden con la API real.

## 4. Interfaz web de campañas e integración en proyectos

- [ ] 4.1 Crear la página `/campaigns` en `apps/web`: listado de campañas con resumen de reglas, botones crear, cargar desde plantilla ES/EN, duplicar y eliminar con confirmación, usando TanStack Query y `packages/api-client`. Verificar con `pnpm --filter web lint && pnpm --filter web build` y prueba manual contra la API local.
- [ ] 4.2 Implementar el editor de campañas (componentes en kebab-case) con formulario estructurado por secciones, validación en vivo, carga de imagen watermark, pestaña "Pegar brief" que llama a `/api/campaigns/parse` y resalta visualmente los campos de `inferred_fields`, y panel de vista previa JSON sincronizado. Verificar con pruebas de flujo manual (brief → revisión de inferidos → edición → guardar) y `pnpm --filter web build`.
- [ ] 4.3 Habilitar el selector de campaña en `/projects/new` (pre-rellenando `requested_clips` e idioma compatibles) y mostrar badges/detalles de `rule_violations` en las tarjetas de clips en `/projects/[id]` sin bloquear reproducción ni edición. Verificar manualmente creando un proyecto con campaña y comprobando que las alertas aparecen en las cards.

## 5. Verificación integrada

- [ ] 5.1 Ejecutar la suite completa: `uv run --project apps/api ruff check . && uv run --project apps/api ruff format --check . && uv run --project apps/api pytest`, `pnpm --filter web lint && pnpm --filter web build`, flujo end-to-end (pegar brief → guardar campaña → crear proyecto con campaña → comprobar selección con `rule_violations` y render con reglas) y `openspec validate add-campaign-rules --strict` sin errores.

## Workflow follow-up

- Revisión del orquestador y del usuario sobre la rama `change/add-campaign-rules`.
- Archivar el change con `openspec archive add-campaign-rules` tras la aprobación.
