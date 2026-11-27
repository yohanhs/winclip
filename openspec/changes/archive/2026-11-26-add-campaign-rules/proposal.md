# Proposal

## Why

El pipeline base selecciona y renderiza clips usando parámetros genéricos, pero en el trabajo real de clipping cada cliente o canal entrega un brief con restricciones estrictas (duración mínima y máxima, temas prioritarios, palabras o temas prohibidos, menciones obligatorias, hashtags, estilo visual, marca de agua y llamado a la acción). Sin campañas estructuradas ni validación automática de reglas, el usuario tiene que reescribir instrucciones manualmente en cada proyecto y revisar cada clip a ojo para detectar incumplimientos.

## What Changes

- Entidad `campaign` persistida por workspace con el esquema completo de reglas definido en `docs/architecture.md §6.4` y validación estricta de rangos, formatos y referencias.
- API REST CRUD en `/api/campaigns`, duplicación de campañas, plantillas predefinidas en español e inglés inspiradas en campañas reales de clipping, subida segura de marca de agua y endpoint `POST /api/campaigns/parse` que convierte un brief en texto libre en reglas propuestas usando el router LLM, marcando qué campos fueron inferidos para revisión humana.
- Integración de campañas con el flujo existente: selector de campaña habilitado en `/projects/new`, inyección de reglas en la selección de clips (`clip-selection`), validación determinista de incumplimientos (`rule_violations`) registrada en cada candidato y clip, y aplicación de reglas de estilo en el render (`subtitle_preset`, `watermark_path`, `cta_text` y `hook_max_seconds`).
- Interfaz web en `/campaigns` con listado, plantillas de ejemplo ES/EN, editor estructurado, pestaña "Pegar brief" con indicadores de campos inferidos, vista previa JSON sincronizada y visualización de `rule_violations` en las tarjetas de clips.

**Fuera de alcance:** importación automática de briefs desde URLs externas (Discord, Whop, Google Docs), publicación en redes sociales (`add-publishers`), gestión de cuentas sociales (`add-social-accounts`), versionado histórico de campañas y permisos multi-usuario.

## Capabilities

### New Capabilities
- `campaign-rules`: definición, validación, parseo asistido desde briefs en texto libre, gestión web/API y aplicación de reglas de campaña sobre la selección, validación y renderizado de clips.

### Modified Capabilities

## Impact

- Backend (`apps/api`): nuevos módulos `winclip/rules/{schema,parser,validator}.py`, router `winclip/routers/campaigns.py`, plantilla de campañas en `assets/campaign-templates/`, tabla `campaign` en SQLite, extensión de `pipeline/select.py`, `pipeline/render.py`, `routers/projects.py` y `worker/handlers.py`.
- Frontend (`apps/web`): páginas y componentes bajo `/campaigns`, habilitación del selector de campaña en `/projects/new`, badges de `rule_violations` en las tarjetas de clips en `/projects/[id]`.
- Cliente tipado (`packages/api-client`): regeneración del cliente OpenAPI con los endpoints de campañas.
- Dependencias: sin nuevas dependencias externas requeridas.
