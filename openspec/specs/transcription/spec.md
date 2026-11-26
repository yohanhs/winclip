# transcription Specification

## Purpose
Transcribe localmente la pista de audio normalizada de un proyecto con marcas temporales a nivel de palabra y persiste el resultado siguiendo el contrato compartido `transcript.json`.

## Requirements

### Requirement: Transcripción con timestamps por palabra
El sistema SHALL transcribir `audio/audio16k.wav` mediante `winclip transcribe <project_id>` y escribir de forma atómica `transcript/transcript.json` conforme al contrato compartido (`language`, `duration`, `model`, `segments` con `id`, `start`, `end`, `text` y `words` con `w`, `s`, `e`, `p`).

#### Scenario: Transcripción exitosa de un proyecto ingestado
- **WHEN** el usuario ejecuta `winclip transcribe <project_id>` sobre un proyecto con `audio/audio16k.wav`
- **THEN** se crea `transcript/transcript.json` válido con segmentos ordenados cronológicamente y cada palabra cumpliendo `0 <= s <= e` y `0 <= p <= 1`

#### Scenario: Proyecto sin audio preparado
- **WHEN** el usuario ejecuta `winclip transcribe <project_id>` sobre un proyecto inexistente o sin `audio/audio16k.wav`
- **THEN** el comando falla con código distinto de 0 e indica que debe ejecutarse `winclip ingest` previamente

### Requirement: Selección y autodetección de idioma
El sistema SHALL aceptar `--language` con los valores `es`, `en` o `auto` (valor por defecto `auto`), forzando el idioma indicado o autodetectándolo y registrando el código resultante en `transcript.json`.

#### Scenario: Idioma explícito en español
- **WHEN** el usuario ejecuta `winclip transcribe <project_id> --language es`
- **THEN** la transcripción se ejecuta fijando español y `transcript.json` registra `"language": "es"`

#### Scenario: Autodetección de idioma
- **WHEN** el usuario ejecuta `winclip transcribe <project_id>` sin `--language` o con `--language auto`
- **THEN** el sistema detecta automáticamente el idioma del audio y lo persiste en el campo `language` de `transcript.json`

#### Scenario: Idioma no soportado
- **WHEN** el usuario ejecuta `winclip transcribe <project_id> --language de`
- **THEN** el comando rechaza el parámetro con código distinto de 0 indicando los valores válidos (`es`, `en`, `auto`)

### Requirement: Selección de modelo de transcripción
El sistema SHALL utilizar por defecto el modelo configurado en `WHISPER_MODEL` y SHALL permitir sobrescribirlo mediante `--model`, aceptando el atajo `tiny` para un modelo ligero de pruebas rápidas.

#### Scenario: Modelo por defecto
- **WHEN** el usuario ejecuta `winclip transcribe <project_id>` sin `--model`
- **THEN** se usa el modelo de `WHISPER_MODEL` y ese identificador queda registrado en el campo `model` de `transcript.json`

#### Scenario: Modelo ligero con atajo tiny
- **WHEN** el usuario ejecuta `winclip transcribe <project_id> --model tiny`
- **THEN** se transcribe usando el modelo ligero configurado y dicho identificador queda registrado en el campo `model` de `transcript.json`

### Requirement: Reanudabilidad e idempotencia
El sistema SHALL omitir el recálculo cuando `transcript/transcript.json` ya existe y es válido, devolviendo el resultado existente salvo que se proporcione la bandera `--force`.

#### Scenario: Reutilización de transcripción existente
- **WHEN** el usuario ejecuta `winclip transcribe <project_id>` sobre un proyecto que ya tiene `transcript/transcript.json` válido sin `--force`
- **THEN** no se invoca el motor de transcripción, el archivo existente se conserva sin cambios y la salida informa que se reutilizó la transcripción previa

#### Scenario: Recálculo forzado con --force
- **WHEN** el usuario ejecuta `winclip transcribe <project_id> --force` sobre un proyecto ya transcrito
- **THEN** el sistema vuelve a ejecutar la transcripción y reemplaza `transcript/transcript.json` de forma atómica

### Requirement: Reporte de progreso en transcripción
La transcripción SHALL aceptar un callback de progreso y reportar avances entre 0 y 100 junto con la etapa en curso, permitiendo mostrar progreso en la CLI y reutilizar la misma interfaz desde el worker futuro.

#### Scenario: Progreso reportado de inicio a fin
- **WHEN** se invoca la transcripción con un callback de progreso registrado
- **THEN** el callback recibe actualizaciones en orden creciente con sus etapas (carga, transcripción y guardado) y alcanza 100 al concluir
