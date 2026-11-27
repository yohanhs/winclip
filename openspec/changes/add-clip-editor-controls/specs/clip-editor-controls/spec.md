# Spec Delta

## Purpose

Permite ajustar por clip individual las palabras de los subtítulos, el preset visual de subtítulos, el modo de reencuadre y los parámetros manuales de cámara desde la API y la web antes de re-renderizar.

## ADDED Requirements

### Requirement: Consulta de palabras del clip
La API SHALL exponer `GET /api/clips/{id}/words` devolviendo la lista ordenada de palabras del rango temporal del clip (índice, texto original, texto efectivo, inicio y fin relativos al clip), reflejando cualquier corrección previamente guardada.

#### Scenario: Lectura de palabras con overrides aplicados
- **WHEN** un cliente consulta `GET /api/clips/{id}/words` para un clip con una corrección guardada en la palabra de índice 3
- **THEN** la respuesta devuelve todas las palabras del tramo con `original` intacto, `text` actualizado en el índice 3 y los timestamps `start` y `end` preservados

#### Scenario: Clip inexistente o sin transcripción
- **WHEN** se consulta `GET /api/clips/{id}/words` para un `id` inexistente o un proyecto sin `transcript.json`
- **THEN** la API devuelve `404` con un mensaje descriptivo

### Requirement: Corrección de palabras de subtítulos por clip
El sistema SHALL permitir guardar correcciones de texto palabra a palabra por clip vía `PATCH /api/clips/{id}` sin modificar `transcript.json` del proyecto, y SHALL usar el texto corregido al generar `.ass` o renderizar con PIL en el siguiente re-render.

#### Scenario: Corrección aplicada al re-renderizar
- **WHEN** el usuario corrige `"Juc"` por `"Hook"` en un clip y ejecuta re-render
- **THEN** el archivo `subs.ass` y el video renderizado muestran `"Hook"` con el mismo timestamp original, mientras `transcript.json` del proyecto permanece inalterado

#### Scenario: Restablecer correcciones
- **WHEN** el usuario limpia las correcciones de subtítulos de un clip y guarda
- **THEN** las palabras vuelven al texto original de la transcripción en el siguiente re-render

### Requirement: Override de preset y modo de reencuadre por clip
El sistema SHALL permitir sobrescribir `subtitle_preset` y `reframe_mode` (`face`, `center`, `blur`, `passthrough`) a nivel de clip individual, heredando los valores del proyecto o campaña cuando no estén definidos en el clip.

#### Scenario: Cambio de preset y reframe en un solo clip
- **WHEN** el usuario asigna `subtitle_preset="clean-white"` y `reframe_mode="blur"` al clip A de un proyecto configurado con `bold-yellow` y `face`, y solicita re-render
- **THEN** el clip A se renderiza con `clean-white` y `blur` (reflejado en `render.json`), mientras los demás clips del proyecto conservan `bold-yellow` y `face`

#### Scenario: Preset o modo inválido
- **WHEN** se envía un `subtitle_preset` inexistente o un `reframe_mode` fuera del catálogo permitido en `PATCH /api/clips/{id}`
- **THEN** la API rechaza la petición con `422` y no modifica el clip

### Requirement: Ajuste manual de encuadre y zoom por clip
El sistema SHALL permitir definir `crop_x_pct` (`0..100`), `crop_y_pct` (`0..100`) y `zoom_pct` (`50..200`) en clips con modo `center` y aplicarlos en el renderizado vertical.

#### Scenario: Reencuadre manual guardado y renderizado
- **WHEN** el usuario configura `reframe_mode="center"`, `crop_x_pct=35`, `crop_y_pct=25` y `zoom_pct=120` en un clip y solicita re-render
- **THEN** el worker invoca el renderizado con esos parámetros exactos y actualiza `clip.mp4` y `thumb.jpg`

#### Scenario: Valores fuera de rango
- **WHEN** se envían valores de `crop_x_pct`, `crop_y_pct` o `zoom_pct` fuera de sus límites permitidos
- **THEN** la API responde con `422` detallando el campo inválido

### Requirement: Controles de edición en la interfaz web
La interfaz web SHALL integrar en el editor del clip en `/projects/[id]` la corrección inline de palabras de subtítulos (con botón restablecer), los selectores de preset y modo de reencuadre por clip, y los deslizadores manuales de `crop X`, `crop Y` y `zoom` visibles cuando el modo es `center`, permitiendo guardar y re-renderizar en un paso.

#### Scenario: Flujo de corrección y re-render en el modal
- **WHEN** el usuario edita una palabra de subtítulo, cambia el modo a `blur` y pulsa `"Guardar y Re-renderizar"`
- **THEN** la interfaz envía `PATCH /api/clips/{id}` seguido de `POST /api/clips/{id}/rerender`, muestra el estado `rendering` en la card y refresca el video al recibir `clip.ready`
