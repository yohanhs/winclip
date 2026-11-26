# clip-selection Specification

## Purpose
Segmenta la transcripción de un proyecto en unidades candidatas respetando límites de palabra, selecciona y puntúa los mejores clips mediante el gateway LLM aplicando reglas configurables y persiste `candidates.json`.

## Requirements

### Requirement: Segmentación alineada a frases y palabras
El sistema SHALL agrupar la transcripción en unidades candidatas basándose en límites de frase y pausas naturales, y SHALL alinear siempre el inicio y fin de cada clip seleccionado a marcas temporales reales de palabras en `transcript.json`.

#### Scenario: Cortes sin partir palabras
- **WHEN** el LLM propone un intervalo cuyos tiempos caen en medio de una palabra
- **THEN** el sistema ajusta `start` y `end` a los límites exactos de palabras existentes en `transcript.json` manteniendo la duración dentro del rango permitido

#### Scenario: Proyecto sin transcripción previa
- **WHEN** el usuario ejecuta `winclip select <project_id> --count 5` sin que exista `transcript/transcript.json`
- **THEN** el comando falla con código distinto de 0 e indica que debe ejecutarse `winclip transcribe` primero

### Requirement: Selección en una pasada o por chunks con ranking global
El sistema SHALL evaluar la transcripción completa en una sola pasada cuando quepa dentro del presupuesto de contexto configurado y SHALL dividirla en chunks con solapamiento seguidos de consolidación y ranking global cuando supere ese límite.

#### Scenario: Video corto evaluado en una pasada
- **WHEN** la transcripción formateada no excede el límite de contexto de una pasada
- **THEN** el selector realiza una única solicitud de selección al gateway LLM y produce `selection/candidates.json`

#### Scenario: Video largo evaluado por chunks con solapamiento
- **WHEN** la transcripción excede el límite de contexto de una pasada
- **THEN** el selector la divide en ventanas solapadas alineadas a frases, evalúa cada ventana y consolida un ranking global sin duplicados ni solapes

### Requirement: Contrato e invariantes de candidates.json
El sistema SHALL escribir `selection/candidates.json` conforme al contrato compartido (`project_id`, `campaign_id`, `requested`, `provider`, `candidates[]`) garantizando sin excepción: ausencia de solapes, `min_duration <= end - start <= max_duration`, cortes alineados a palabras y orden descendente por `score`.

#### Scenario: Selección de cantidad fija con --count N
- **WHEN** el usuario ejecuta `winclip select <project_id> --count 5`
- **THEN** se genera `selection/candidates.json` con `"requested": 5`, un máximo de 5 candidatos sin solapes, ordenados de mayor a menor `score` y cumpliendo los límites de duración y alineación a palabras

#### Scenario: Selección exhaustiva con --count max
- **WHEN** el usuario ejecuta `winclip select <project_id> --count max`
- **THEN** se incluyen todos los candidatos no solapados que superan el umbral de puntuación configurado y no presentan infracciones de reglas, ordenados por `score` descendente

### Requirement: Aplicación y validación de reglas opcionales
El sistema SHALL aceptar `--rules <ruta.json>` conforme al esquema de reglas de campaña, inyectar sus directrices en el prompt de selección y validar los candidatos post-LLM en duración, `banned_words` y `required_keywords`.

#### Scenario: Descarte por palabras prohibidas
- **WHEN** se ejecuta `winclip select` con un archivo de reglas que define `banned_words` y el LLM propone un clip que contiene alguna de ellas
- **THEN** la validación post-LLM descarta ese candidato y no aparece en `selection/candidates.json`

#### Scenario: Validación de palabras clave requeridas
- **WHEN** las reglas definen `required_keywords` y un candidato propuesto no contiene ninguna de esas palabras clave
- **THEN** el validador registra la infracción en `rule_violations` y el modo `--count max` excluye dicho candidato

#### Scenario: Archivo de reglas inexistente o inválido
- **WHEN** el usuario pasa `--rules` apuntando a un archivo ausente o con esquema inválido
- **THEN** el comando falla antes de invocar al gateway LLM, muestra el error de validación y sale con código distinto de 0

### Requirement: Idioma de metadatos generados
El sistema SHALL generar `title`, `hook`, `description` y `hashtags` en el idioma de `transcript.json` salvo que el archivo de reglas defina un idioma explícito distinto de `auto`.

#### Scenario: Idioma heredado del video
- **WHEN** `transcript.json` tiene `"language": "es"` y no hay regla de idioma o esta es `"auto"`
- **THEN** los prompts piden metadatos en español y cada candidato en `candidates.json` registra `"language": "es"`

#### Scenario: Idioma forzado por regla
- **WHEN** `transcript.json` está en inglés y las reglas especifican `"language": "es"`
- **THEN** los prompts piden metadatos en español y cada candidato registra `"language": "es"`

### Requirement: Prompts versionados e invalidación de caché
El sistema SHALL mantener los prompts de selección en archivos versionados dedicados e incluir su identificador de versión en la clave de caché para invalidar respuestas antiguas al modificar un prompt.

#### Scenario: Cambio de versión del prompt
- **WHEN** se actualiza la versión de un prompt de selección
- **THEN** una nueva ejecución de `winclip select` genera una clave de caché distinta y no reutiliza respuestas cacheadas de la versión anterior
