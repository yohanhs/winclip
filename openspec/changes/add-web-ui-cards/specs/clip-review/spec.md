# Spec Delta

## Purpose

Ofrece la pantalla de revisión de proyecto y sus clips generados en formato vertical 9:16, integrando seguimiento en tiempo real de las etapas del pipeline, vista previa rápida, edición de metadatos, recorte con re-renderizado, descarga, eliminación y multiselección preparada para publicación.

## ADDED Requirements

### Requirement: Seguimiento en vivo de las etapas del pipeline
La ruta `/projects/[id]` SHALL mostrar las cuatro etapas del procesamiento (`Descarga`, `Transcripción`, `Selección`, `Render`) con su estado actual y porcentaje de avance actualizados en tiempo real mediante eventos SSE, permitiendo cancelar el trabajo activo y mostrando claramente cualquier error si el proceso falla.

#### Scenario: Avance en tiempo real de etapas y aparición progresiva de clips
- **WHEN** un proyecto está en procesamiento en `/projects/[id]` y el servidor emite eventos `job.progress` y `clip.ready`
- **THEN** la barra de etapas avanza reflejando la etapa activa y su porcentaje, y cada clip listo aparece en el grid sin recargar la página

#### Scenario: Cancelación del procesamiento desde la vista de detalle
- **WHEN** el usuario pulsa cancelar sobre un trabajo en curso y confirma
- **THEN** se solicita la cancelación a la API, se muestra notificación y el estado de etapas pasa a cancelado

#### Scenario: Visualización de fallo del pipeline
- **WHEN** el servidor emite `job.failed` o el proyecto carga en estado fallido
- **THEN** la vista destaca la etapa fallida y muestra el mensaje de error legible devuelto por la API

### Requirement: Grid de cards 9:16 con preview hover-play
La vista `/projects/[id]` SHALL presentar los clips en un grid responsive de tarjetas verticales con relación de aspecto `9:16`, mostrando miniatura, reproducción silenciada automática al pasar el cursor (`hover-play`), opción de reproducción interactiva con audio, puntuación (`score`), título, `hook`, duración formateada y hashtags.

#### Scenario: Reproducción rápida al pasar el cursor
- **WHEN** el usuario sitúa el cursor sobre la vista previa de una card de clip renderizado y luego lo retira
- **THEN** el video inicia su reproducción silenciada al entrar y se pausa reiniciando la vista previa al salir

#### Scenario: Lectura completa de metadatos en la card
- **WHEN** existen clips renderizados en el proyecto
- **THEN** cada card muestra su relación 9:16, badge de `score`, título, texto `hook`, duración formateada y lista de hashtags

#### Scenario: Estados vacío y cargando del grid
- **WHEN** el proyecto aún está cargando o terminó sin clips disponibles
- **THEN** se muestran esqueletos de cards 9:16 durante la carga o un estado vacío descriptivo cuando no hay clips

### Requirement: Edición de metadatos de clip
Cada card de clip SHALL permitir editar `title`, `description` y `hashtags`, validando los campos antes de guardar, persistiendo los cambios en la API y mostrando retroalimentación mediante toast.

#### Scenario: Guardado exitoso de metadatos
- **WHEN** el usuario edita el título, la descripción y los hashtags de un clip y confirma el guardado
- **THEN** los cambios se envían a la API, la card refleja inmediatamente los nuevos valores y aparece un toast de confirmación

#### Scenario: Error al guardar metadatos
- **WHEN** la API rechaza la actualización de metadatos
- **THEN** la interfaz muestra un toast con el motivo del error y permite corregir o reintentar sin perder lo editado

### Requirement: Ajuste de inicio y fin con mini timeline y re-renderizado
Cada clip SHALL ofrecer un control de ajuste temporal con una mini línea de tiempo interactiva para modificar `start` y `end` dentro de la duración del video fuente, validando `0 <= start < end`, guardando los nuevos límites y lanzando su re-renderizado con indicador visual hasta recibir la nueva versión.

#### Scenario: Recorte y solicitud de re-render
- **WHEN** el usuario ajusta el inicio y el fin de un clip en la mini timeline a un rango válido y pulsa re-renderizar
- **THEN** la aplicación guarda los nuevos tiempos, encola el re-render, muestra la card en estado de re-renderizado y actualiza su video y duración al llegar `clip.ready`

#### Scenario: Prevención de rango temporal inválido
- **WHEN** el usuario intenta establecer un inicio mayor o igual que el fin
- **THEN** el control impide enviar la solicitud e indica el error de rango

### Requirement: Descarga y eliminación individual de clips
Cada card de clip SHALL incluir acciones para descargar el archivo de video del clip y para eliminarlo previa confirmación, actualizando el grid sin recargar la página.

#### Scenario: Descarga directa de un clip
- **WHEN** el usuario activa la acción de descargar en un clip renderizado
- **THEN** el navegador inicia la descarga del archivo MP4 correspondiente al clip

#### Scenario: Eliminación de un clip con confirmación
- **WHEN** el usuario elige eliminar un clip y confirma en el diálogo
- **THEN** la API elimina el clip, la card desaparece del grid y se muestra un toast de confirmación

### Requirement: Multiselección de clips preparada para publicación
La vista `/projects/[id]` SHALL permitir seleccionar múltiples clips mediante casillas en las cards (incluyendo seleccionar todos y limpiar selección) mostrando una barra contextual con el conteo de seleccionados y un botón `"Publicar"` deshabilitado con indicación de disponibilidad futura.

#### Scenario: Selección múltiple y botón Publicar deshabilitado
- **WHEN** el usuario selecciona dos o más cards en el grid
- **THEN** aparece la barra de acciones con el contador de clips seleccionados y el botón `"Publicar"` visiblemente deshabilitado con un mensaje indicando que estará disponible al habilitar los publicadores
