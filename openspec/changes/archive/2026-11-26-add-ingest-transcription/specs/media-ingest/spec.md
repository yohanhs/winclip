# Spec Delta

## Purpose

Permite incorporar un video largo desde una URL remota o un archivo local en un proyecto aislado en disco, extraer sus metadatos técnicos y generar una pista de audio normalizada lista para transcripción.

## ADDED Requirements

### Requirement: Creación de estructura de proyecto
El sistema SHALL crear el directorio `STORAGE_DIR/projects/<project_id>/` con las subcarpetas `source/` y `audio/`, generando un identificador único en minúsculas cuando no se indique `--project-id` o usando el identificador proporcionado si es válido.

#### Scenario: Ingesta con identificador automático
- **WHEN** el usuario ejecuta `winclip ingest <fuente>` sin `--project-id`
- **THEN** el sistema genera un identificador único en minúsculas, crea `STORAGE_DIR/projects/<project_id>/source/` y `audio/`, y muestra el `project_id` creado

#### Scenario: Identificador explícito inválido
- **WHEN** el usuario ejecuta `winclip ingest <fuente> --project-id ../escape`
- **THEN** el comando falla con código de salida distinto de 0, informa que el identificador es inválido y no crea archivos fuera de `STORAGE_DIR`

#### Scenario: Proyecto ya existente sin forzar
- **WHEN** el usuario ejecuta `winclip ingest <fuente> --project-id <id>` sobre un proyecto que ya tiene `source/meta.json` sin indicar `--force`
- **THEN** el sistema rechaza sobrescribir el proyecto con código distinto de 0 y sugiere usar `--force`

### Requirement: Ingesta desde URL remota
El sistema SHALL descargar videos desde URLs remotas soportadas mediante `winclip ingest <url>` en el mejor formato MP4 con altura máxima de 1080p hacia `source/original.mp4` y capturar los metadatos de título, canal y duración.

#### Scenario: Descarga exitosa desde URL
- **WHEN** el usuario ejecuta `winclip ingest <url_valida>` sobre un video público disponible
- **THEN** el sistema guarda `source/original.mp4` con altura menor o igual a 1080 píxeles y registra `source_type: "url"`, `source_url`, `title`, `channel` y `duration` en `source/meta.json`

#### Scenario: URL inválida o no soportada
- **WHEN** el usuario ejecuta `winclip ingest https://ejemplo.invalido/no-video`
- **THEN** el comando falla con código distinto de 0 indicando que la URL es inválida o no soportada y no escribe `source/meta.json`

#### Scenario: Video privado o restringido
- **WHEN** el usuario intenta ingestar una URL cuyo video es privado o inaccesible sin autenticación
- **THEN** el comando falla con código distinto de 0 con un mensaje claro indicando que el video es privado o no disponible

#### Scenario: Transmisión en directo en curso
- **WHEN** el usuario intenta ingestar una URL correspondiente a una transmisión en vivo activa
- **THEN** el sistema rechaza la descarga antes de iniciar la transferencia, informa que los directos en curso no están soportados y termina con código distinto de 0

### Requirement: Ingesta desde archivo local
El sistema SHALL aceptar archivos locales con extensión `.mp4`, `.mov`, `.mkv` o `.webm` mediante `winclip ingest <ruta>` y copiarlos a `source/original.<ext>` preservando intacto el archivo original.

#### Scenario: Copia de archivo local soportado
- **WHEN** el usuario ejecuta `winclip ingest /ruta/video.mov` sobre un archivo legible
- **THEN** el archivo se copia a `source/original.mov`, el archivo de origen permanece sin modificaciones y `source/meta.json` registra `source_type: "file"` y el título derivado del nombre

#### Scenario: Archivo inexistente o extensión no soportada
- **WHEN** el usuario ejecuta `winclip ingest /ruta/inexistente.mp4` o pasa un archivo `.txt`
- **THEN** el comando falla con código distinto de 0 indicando el motivo y no crea `source/meta.json`

### Requirement: Extracción de metadatos técnicos
El sistema SHALL inspeccionar el video ingestado con el binario configurado en `FFPROBE_BIN` y escribir `source/meta.json` de forma atómica con duración, resolución, fotogramas por segundo, códecs y presencia de audio.

#### Scenario: Video con pista de audio válida
- **WHEN** se ingesta un video con pistas de video y audio válidas
- **THEN** `source/meta.json` contiene `project_id`, `source_type`, `duration`, `width`, `height`, `fps`, `video_codec`, `audio_codec`, `has_audio: true` y `file_size_bytes`

#### Scenario: Video sin pista de audio
- **WHEN** se ingesta un video que carece de pista de audio
- **THEN** la ingesta falla con código distinto de 0 indicando que el video no contiene audio para transcribir y no deja el proyecto marcado como listo

### Requirement: Extracción de audio normalizado
El sistema SHALL extraer el audio del video ingestado usando el ejecutable configurado en `FFMPEG_BIN` y guardarlo en `audio/audio16k.wav` como WAV PCM mono a 16000 Hz.

#### Scenario: Extracción correcta de audio
- **WHEN** la inspección técnica confirma que el video tiene pista de audio
- **THEN** se genera `audio/audio16k.wav` con 1 canal, frecuencia de muestreo de 16000 Hz y duración coherente con la del video original

### Requirement: Reporte de progreso en ingesta
La operación de ingesta SHALL emitir notificaciones de progreso mediante callback en un rango de 0 a 100 acompañadas del nombre de la etapa activa (`download` o `copy`, `probe`, `extract_audio`).

#### Scenario: Avance monótono hasta completar
- **WHEN** se ejecuta la ingesta con un callback de progreso registrado
- **THEN** el callback recibe valores crecientes entre 0 y 100 con las etapas correspondientes y culmina en 100 al finalizar con éxito
