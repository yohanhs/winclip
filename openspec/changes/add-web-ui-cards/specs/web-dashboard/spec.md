# Spec Delta

## Purpose

Proporciona el cliente tipado generado desde el contrato de la API y la experiencia web oscura y responsive para consultar proyectos en tiempo real y crear nuevos proyectos desde URL o archivo local con previsualización de subtítulos.

## ADDED Requirements

### Requirement: Cliente API tipado generado desde OpenAPI
El monorepo SHALL generar un cliente tipado en `packages/api-client` mediante el comando `pnpm gen:api` a partir de la especificación OpenAPI del backend, exponiendo operaciones y modelos fuertemente tipados sin tipos `any` para su consumo en la aplicación web.

#### Scenario: Generación reproducible del cliente tipado
- **WHEN** se ejecuta `pnpm gen:api`
- **THEN** se regeneran las definiciones de tipos y el cliente en `packages/api-client` alineados con los `operationId` de la API y la compilación estricta de la web pasa sin errores

### Requirement: Listado de proyectos con progreso en vivo
La ruta `/projects` SHALL mostrar la lista de proyectos con título, insignia de estado, miniatura (o marcador visual si aún no existe), cantidad de clips generados y barra de progreso actualizada en vivo ante eventos SSE, permitiendo abrir cada proyecto, crear uno nuevo o eliminar uno existente con confirmación.

#### Scenario: Actualización en vivo de un proyecto en proceso
- **WHEN** el usuario visualiza `/projects` y llega un evento de progreso o finalización para un proyecto en ejecución
- **THEN** la tarjeta o fila del proyecto actualiza su porcentaje, etapa, estado y conteo de clips sin recargar la página

#### Scenario: Eliminación de proyecto con confirmación
- **WHEN** el usuario solicita eliminar un proyecto desde `/projects` y confirma la acción en el diálogo
- **THEN** el proyecto desaparece del listado y se muestra una notificación de confirmación

#### Scenario: Estados vacío, cargando y de error
- **WHEN** no existen proyectos, la consulta está en curso o la API devuelve un error
- **THEN** `/projects` muestra respectivamente un estado vacío con botón para crear proyecto, esqueletos de carga o un aviso de error con acción de reintento

### Requirement: Creación de proyectos desde URL o subida de archivo
La ruta `/projects/new` SHALL ofrecer dos pestañas excluyentes, `URL` y `Subir archivo`, soportando arrastrar y soltar (drag & drop) en la pestaña de archivo, validación previa al envío y barra de progreso porcentual real durante la carga, redirigiendo a `/projects/[id]` al completarse.

#### Scenario: Creación mediante URL válida
- **WHEN** el usuario selecciona la pestaña `URL`, introduce una dirección de video válida y envía el formulario
- **THEN** se crea el proyecto en la API, se muestra una notificación de éxito y la aplicación navega a `/projects/[id]`

#### Scenario: Subida de archivo con drag & drop y progreso
- **WHEN** el usuario arrastra un archivo de video válido a la zona de carga en `Subir archivo` y envía el formulario
- **THEN** la interfaz muestra el progreso porcentual real de la subida hasta completarla y luego navega a `/projects/[id]`

#### Scenario: Error de validación o de red al crear
- **WHEN** el usuario intenta enviar sin URL ni archivo o la API rechaza la solicitud con error
- **THEN** el formulario muestra el mensaje de error legible junto al campo o en una notificación sin perder los valores ingresados

### Requirement: Configuración de parámetros y preview de presets de subtítulos
El formulario de `/projects/new` SHALL permitir configurar la cantidad de clips mediante un deslizador numérico o la opción `"Máximo posible"`, el idioma (`auto`, `es`, `en`), el modo de reframe y el preset de subtítulos con una vista previa visual en vivo; el selector de campaña SHALL mostrarse visible pero deshabilitado con un aviso de disponibilidad futura.

#### Scenario: Alternancia entre cantidad fija y máximo posible
- **WHEN** el usuario activa `"Máximo posible"` en el selector de cantidad de clips
- **THEN** el deslizador numérico queda deshabilitado y el formulario envía `"max"` como `requested_clips`

#### Scenario: Vista previa interactiva de preset de subtítulos
- **WHEN** el usuario cambia el preset de subtítulos seleccionado
- **THEN** la vista previa muestra texto karaoke de ejemplo reflejando los estilos visuales del preset elegido

#### Scenario: Selector de campaña deshabilitado hasta su fase
- **WHEN** el usuario abre `/projects/new`
- **THEN** el campo de campaña aparece deshabilitado con una etiqueta explicativa indicando que estará disponible en un próximo módulo

### Requirement: Diseño oscuro moderno, responsive y retroalimentación global
La aplicación web SHALL presentar un tema oscuro moderno y legible en escritorio y móvil, mantener una navegación fluida entre secciones y comunicar el resultado de acciones y errores mediante notificaciones (toasts) no bloqueantes.

#### Scenario: Uso en pantalla móvil y escritorio
- **WHEN** el usuario abre `/projects` o `/projects/new` en un ancho de viewport móvil y en escritorio
- **THEN** la distribución se adapta sin desbordamiento horizontal y todos los controles permanecen accesibles
