# Spec Delta

## Purpose

Expone la API HTTP REST y el canal de eventos en tiempo real (SSE) para crear, consultar, modificar y eliminar proyectos y clips, entregar archivos multimedia de forma segura con soporte Range y proveer un contrato OpenAPI estable para clientes.

## ADDED Requirements

### Requirement: Creación de proyectos por URL o subida en streaming
La API SHALL aceptar en `POST /api/projects` la creación de proyectos desde una URL o mediante carga multipart en streaming de archivos grandes sin cargarlos completos en memoria, recibiendo `requested_clips` (entero positivo o `"max"`), `language`, `campaign_id` opcional, `subtitle_preset` y `reframe_mode`, y SHALL encolar un trabajo `pipeline`.

#### Scenario: Crear proyecto a partir de URL
- **WHEN** un cliente envía `POST /api/projects` con `source_type` igual a `url`, una URL válida, `requested_clips` igual a `5` y `language` igual a `es`
- **THEN** la API responde `201` con los datos del proyecto creado y el identificador del trabajo `pipeline` en estado `queued`

#### Scenario: Crear proyecto subiendo archivo grande en streaming
- **WHEN** un cliente envía `POST /api/projects` en formato multipart con un archivo de video válido y `requested_clips` igual a `"max"`
- **THEN** el archivo se guarda de forma incremental en `storage/projects/<project_id>/source/`, la API responde `201` y el trabajo `pipeline` queda encolado

#### Scenario: Rechazo de entrada inválida
- **WHEN** un cliente envía `POST /api/projects` sin URL ni archivo, con `requested_clips` menor que 1, con idioma no soportado o con un archivo vacío o extensión no permitida
- **THEN** la API responde `400` o `422` con detalle del error y no deja registros ni archivos huérfanos en disco

### Requirement: Consulta y eliminación de proyectos
La API SHALL listar proyectos en `GET /api/projects` con estado, miniatura, conteo de clips y progreso activo, devolver el detalle completo en `GET /api/projects/{id}` y eliminar un proyecto en `DELETE /api/projects/{id}` cancelando sus trabajos activos y borrando sus registros y archivos en disco.

#### Scenario: Listado de proyectos con resumen
- **WHEN** un cliente solicita `GET /api/projects`
- **THEN** la API responde `200` con los proyectos ordenados del más reciente al más antiguo, incluyendo estado, cantidad de clips, miniatura disponible y progreso del último trabajo

#### Scenario: Consulta de proyecto inexistente
- **WHEN** un cliente solicita `GET /api/projects/{id}` con un identificador que no existe
- **THEN** la API responde `404`

#### Scenario: Eliminación completa de proyecto
- **WHEN** un cliente solicita `DELETE /api/projects/{id}` para un proyecto existente
- **THEN** la API cancela sus trabajos pendientes o activos, elimina el proyecto y sus clips de la base de datos, borra su carpeta bajo el directorio de almacenamiento y responde `204`

### Requirement: Gestión, edición y re-renderizado de clips
La API SHALL listar los clips de un proyecto en `GET /api/projects/{id}/clips`, permitir editar `title`, `description`, `hashtags`, `start` y `end` vía `PATCH /api/clips/{id}`, eliminar un clip en `DELETE /api/clips/{id}` y encolar su re-renderizado con `POST /api/clips/{id}/rerender`.

#### Scenario: Edición válida de metadatos y tiempos
- **WHEN** un cliente envía `PATCH /api/clips/{id}` con título actualizado, lista de hashtags y un intervalo donde `0 <= start < end`
- **THEN** la API persiste los cambios y responde `200` con el clip actualizado

#### Scenario: Rechazo de tiempos inválidos
- **WHEN** un cliente envía `PATCH /api/clips/{id}` con `start >= end` o tiempos negativos
- **THEN** la API responde `422` sin alterar el clip persistido

#### Scenario: Solicitud de re-renderizado de clip
- **WHEN** un cliente envía `POST /api/clips/{id}/rerender` sobre un clip existente
- **THEN** la API encola un trabajo de tipo `render` con los tiempos y configuración actuales del clip y responde `202` con los datos del trabajo

#### Scenario: Eliminación individual de clip
- **WHEN** un cliente envía `DELETE /api/clips/{id}` sobre un clip existente
- **THEN** la API borra el registro del clip y sus archivos en disco, responde `204` y mantiene intactos los demás clips del proyecto

### Requirement: Entrega segura de video y miniatura con soporte Range
La API SHALL servir el video de un clip en `GET /api/clips/{id}/file` y su miniatura en `GET /api/clips/{id}/thumb` soportando peticiones HTTP `Range` (`206 Partial Content` y `Accept-Ranges: bytes`) y SHALL bloquear cualquier intento de lectura fuera del directorio de almacenamiento autorizado.

#### Scenario: Solicitud parcial con cabecera Range
- **WHEN** un cliente solicita `GET /api/clips/{id}/file` incluyendo la cabecera `Range: bytes=0-1023`
- **THEN** la API responde `206 Partial Content` con `Content-Range`, `Accept-Ranges: bytes` y exactamente los 1024 bytes solicitados

#### Scenario: Protección contra path traversal
- **WHEN** la ruta resuelta para un archivo de clip o miniatura apunta fuera del directorio `STORAGE_DIR` o contiene saltos de directorio no permitidos
- **THEN** la API rechaza la entrega con `403` o `404` sin leer ni exponer archivos del sistema

#### Scenario: Archivo no disponible
- **WHEN** un cliente solicita el video o la miniatura de un clip que aún no ha sido renderizado o cuyo archivo no existe
- **THEN** la API responde `404`

### Requirement: Catálogo de presets de subtítulos
La API SHALL exponer en `GET /api/presets` los presets de subtítulos disponibles con su identificador, nombre legible y propiedades visuales para que los clientes puedan seleccionarlos y previsualizarlos.

#### Scenario: Consulta del catálogo de presets
- **WHEN** un cliente solicita `GET /api/presets`
- **THEN** la API responde `200` con la lista de presets cargados desde la carpeta de presets del proyecto

### Requirement: Consulta y cancelación de trabajos
La API SHALL exponer el estado de cualquier trabajo en `GET /api/jobs/{id}` y permitir solicitar su cancelación en `POST /api/jobs/{id}/cancel`.

#### Scenario: Consulta de estado de trabajo
- **WHEN** un cliente solicita `GET /api/jobs/{id}` para un trabajo existente
- **THEN** la API responde `200` con `id`, `project_id`, `type`, `status`, `progress`, `stage`, `attempts`, `error` y marcas temporales

#### Scenario: Cancelación aceptada
- **WHEN** un cliente envía `POST /api/jobs/{id}/cancel` para un trabajo en estado `queued` o `running`
- **THEN** la API registra la cancelación y responde `200` con el trabajo actualizado

#### Scenario: Cancelación rechazada en estado terminal
- **WHEN** un cliente envía `POST /api/jobs/{id}/cancel` para un trabajo en estado `done` o `failed`
- **THEN** la API responde `409` indicando que el trabajo ya finalizó

### Requirement: Stream de eventos en tiempo real vía SSE
La API SHALL ofrecer un stream Server-Sent Events (`text/event-stream`) en `GET /api/events` (con filtro opcional `project_id`) que emita eventos `job.progress`, `job.done`, `job.failed`, `clip.ready` y `heartbeat` periódico.

#### Scenario: Entrega de eventos de progreso y clip listo
- **WHEN** un cliente se suscribe a `GET /api/events?project_id=<id>` durante la ejecución de un pipeline
- **THEN** recibe en tiempo real eventos `job.progress`, `clip.ready` por cada clip finalizado y `job.done` (o `job.failed` en caso de error) en formato SSE válido

#### Scenario: Emisión periódica de heartbeat
- **WHEN** no se producen cambios de estado durante el intervalo de latido configurado
- **THEN** el servidor emite un evento `heartbeat` para mantener abierta la conexión

### Requirement: Contrato OpenAPI con operationId estables
La API SHALL generar en `/openapi.json` un esquema OpenAPI válido en el que cada endpoint bajo `/api` declare un `operationId` explícito, único y estable para la generación de clientes tipados.

#### Scenario: Verificación de operationId en el esquema OpenAPI
- **WHEN** un cliente descarga `/openapi.json`
- **THEN** todas las operaciones bajo `/api` tienen un `operationId` explícito y único sin sufijos automáticos de ruta
