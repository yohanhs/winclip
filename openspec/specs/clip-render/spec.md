# clip-render Specification

## Purpose
Orquesta el renderizado completo de uno o varios candidatos de un proyecto en clips verticales 9:16 listos para publicación, generando video, miniatura, subtítulos y manifiesto `render.json` con ejecución idempotente y progreso reportable.

## Requirements

### Requirement: Comando CLI de renderizado y artefactos de salida
El sistema SHALL exponer el comando `winclip render <project_id>` con soporte para `--clip <candidate_id>` o `--all`, `--preset`, `--reframe face|center|blur`, `--engine ass|pil` y `--force`, produciendo en `storage/projects/<project_id>/clips/<clip_id>/` exactamente `clip.mp4`, `thumb.jpg`, `subs.ass` y `render.json` conforme a `docs/architecture.md §6.3`.

#### Scenario: Renderizado de un candidato específico
- **WHEN** el usuario ejecuta `winclip render <project_id> --clip <candidate_id> --preset bold-yellow --reframe face --engine ass` sobre un proyecto con fuente, transcripción y candidatos válidos
- **THEN** se crean `clip.mp4`, `thumb.jpg`, `subs.ass` y `render.json` con el esquema exacto de `docs/architecture.md §6.3` y el comando termina con código 0

#### Scenario: Renderizado en lote de todos los candidatos
- **WHEN** el usuario ejecuta `winclip render <project_id> --all`
- **THEN** el sistema procesa todos los candidatos de `candidates.json` en orden y muestra un resumen final con la ruta de cada clip generado

#### Scenario: Validación de argumentos y prerrequisitos faltantes
- **WHEN** el usuario omite tanto `--clip` como `--all`, pasa ambos a la vez, o falta `transcript.json` o `candidates.json` en el proyecto
- **THEN** el comando termina con código distinto de 0 y un mensaje claro indicando qué argumento o paso previo falta

### Requirement: Especificaciones técnicas de video y audio
El sistema SHALL codificar `clip.mp4` a `1080x1920`, `30 fps` (o la tasa original del video si es menor o igual a `30 fps`), video H.264 acelerado por hardware cuando esté disponible y audio AAC a `192 kbps` normalizado a `-14 LUFS`, ejecutando el flujo en una sola pasada de codificación siempre que sea posible.

#### Scenario: Video origen a 60 fps
- **WHEN** se renderiza un candidato proveniente de un video a `60 fps`
- **THEN** el archivo `clip.mp4` tiene resolución `1080x1920`, tasa de `30 fps`, pista de video H.264 y pista de audio AAC a `192 kbps` normalizada en torno a `-14 LUFS`

#### Scenario: Video origen a 24 fps
- **WHEN** se renderiza un candidato proveniente de un video a `24 fps`
- **THEN** el archivo `clip.mp4` conserva `24 fps` sin interpolar fotogramas artificiales y lo refleja en `render.json`

### Requirement: Overlay de hook y marca de agua opcional
El sistema SHALL permitir superponer el texto `hook` del candidato durante los primeros N segundos en la zona superior segura (reflejando `hook_overlay` en `render.json`) y superponer una imagen de marca de agua opcional en una esquina segura sin obstruir los subtítulos.

#### Scenario: Clip con overlay de hook activo
- **WHEN** se renderiza un candidato que tiene texto `hook` con el overlay habilitado
- **THEN** el texto aparece visible en la parte superior durante los primeros N segundos del clip, desaparece después y `render.json` registra `"hook_overlay": true`

#### Scenario: Clip con marca de agua válida o inexistente
- **WHEN** el usuario pasa `--watermark` con una ruta inexistente
- **THEN** el sistema falla antes de codificar informando que el archivo de marca de agua no existe

### Requirement: Miniatura representativa del clip
El sistema SHALL generar `thumb.jpg` en formato `1080x1920` seleccionando un fotograma nítido del clip que priorice la presencia clara de un rostro, con respaldo a un fotograma nítido no negro cuando no existan rostros.

#### Scenario: Miniatura con rostro detectado
- **WHEN** se completa el renderizado de un clip donde aparece un hablante
- **THEN** `thumb.jpg` es una imagen JPEG válida de `1080x1920` extraída de un fotograma con rostro visible y enfocada con el mismo encuadre que el video

#### Scenario: Miniatura en clip sin rostros
- **WHEN** el clip no contiene rostros detectables
- **THEN** `thumb.jpg` se genera igualmente a partir de un fotograma nítido no negro del clip sin fallar

### Requirement: Idempotencia y escrituras atómicas
El sistema SHALL omitir el re-renderizado cuando ya exista un clip completo para el mismo candidato con parámetros y entradas idénticos, salvo que se especifique `--force`, y SHALL garantizar que un fallo a mitad de ejecución no deje artefactos corruptos en el directorio final del clip.

#### Scenario: Re-ejecución con parámetros idénticos
- **WHEN** se ejecuta `winclip render <project_id> --clip <candidate_id>` dos veces consecutivas con las mismas opciones
- **THEN** la segunda ejecución detecta el render previo vigente, evita recodificar el video y devuelve el clip existente

#### Scenario: Re-renderizado forzado o con cambio de preset
- **WHEN** se ejecuta nuevamente el comando con `--force` o cambiando `--preset`
- **THEN** el sistema vuelve a renderizar el clip y actualiza los artefactos de salida de forma atómica

### Requirement: Reporte de progreso y meta de rendimiento
El sistema SHALL emitir eventos de progreso monotónicos entre `0` y `100` mediante un callback invocable tanto por la CLI como por el worker futuro, y SHALL completar el renderizado de un clip de 60 segundos en menos de 60 segundos en Apple Silicon M1 con el motor por defecto.

#### Scenario: Seguimiento de progreso durante el render
- **WHEN** se invoca la función de renderizado con un callback de progreso
- **THEN** el callback recibe actualizaciones crecientes desde el inicio hasta `100` cubriendo las fases de reencuadre, subtítulos, codificación y miniatura

#### Scenario: Rendimiento objetivo en Apple Silicon M1
- **WHEN** se renderiza un clip de 60 segundos a `1080p` con modo `face`, motor `ass` y codificación acelerada por hardware en M1
- **THEN** el tiempo total de extremo a extremo es inferior a 60 segundos
