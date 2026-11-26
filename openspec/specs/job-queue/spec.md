# job-queue Specification

## Purpose
Gestiona la persistencia y ejecución asíncrona de trabajos del pipeline de clipping en un proceso worker separado, garantizando exclusividad de recursos pesados, reintentos con backoff, cancelación, reporte de progreso y recuperación tras cierres inesperados.

## Requirements

### Requirement: Persistencia de trabajos y entidades base
El sistema SHALL persistir workspaces, proyectos, clips y trabajos en almacenamiento duradero local y SHALL crear automáticamente un workspace por defecto al iniciar si no existe, permitiendo que la cola sobreviva a reinicios del servidor y del worker.

#### Scenario: Arranque inicial crea workspace por defecto
- **WHEN** el backend inicia contra una base de datos recién migrada sin registros
- **THEN** existe exactamente un workspace por defecto listo para asociar nuevos proyectos y un reinicio posterior no crea duplicados

#### Scenario: Cola persistente tras reinicio
- **WHEN** se encola un trabajo y se detienen y reinician tanto el servidor de API como el worker
- **THEN** el trabajo permanece en estado `queued` y es procesado normalmente al reanudarse el worker

### Requirement: Tipos de trabajo y encadenamiento del pipeline
La cola SHALL admitir trabajos de tipo `ingest`, `transcribe`, `select`, `render`, `pipeline` y `publish` (reservado). Un trabajo `pipeline` SHALL ejecutar secuencialmente ingesta, transcripción, selección y renderizado, creando y actualizando los clips del proyecto en cada fase.

#### Scenario: Ejecución completa de un pipeline
- **WHEN** el worker procesa un trabajo `pipeline` válido para un proyecto
- **THEN** recorre secuencialmente las etapas `ingest`, `transcribe`, `select` y `render`, persiste los clips renderizados y termina en estado `done` con progreso `100`

#### Scenario: Tipo de trabajo publish reservado
- **WHEN** el worker toma un trabajo de tipo `publish` antes de existir publicadores habilitados
- **THEN** marca el trabajo como `failed` sin reintentos con un error claro indicando que el tipo `publish` está reservado para una fase posterior

### Requirement: Reclamo atómico y control de concurrencia
El worker SHALL ejecutarse como proceso independiente mediante `winclip worker` (también incluido en `pnpm dev`), SHALL reclamar trabajos de forma atómica sin ejecuciones duplicadas y SHALL ejecutar como máximo un trabajo pesado a la vez (`transcribe`, `render` y las fases pesadas de `pipeline`), permitiendo concurrencia configurable para trabajos ligeros.

#### Scenario: Exclusividad de trabajos pesados
- **WHEN** hay dos trabajos de tipo `transcribe` o `render` en estado `queued` simultáneamente
- **THEN** solo uno pasa a estado `running` a la vez y el segundo permanece en `queued` hasta que el primero libere el recurso pesado

#### Scenario: Concurrencia en trabajos ligeros
- **WHEN** el límite de concurrencia ligera está configurado en 2 y existen dos trabajos `ingest` encolados
- **THEN** ambos trabajos se ejecutan en paralelo sin bloquearse entre sí

#### Scenario: Sin doble reclamo entre workers
- **WHEN** dos instancias del worker intentan reclamar trabajos simultáneamente con un único trabajo encolado
- **THEN** solo una instancia obtiene el bloqueo y ejecuta el trabajo mientras la otra permanece en espera

### Requirement: Progreso y etapas persistidos
Durante la ejecución de cada trabajo, el worker SHALL persistir continuamente el porcentaje de progreso (`0` a `100`), el nombre de la etapa activa y las marcas temporales de creación, inicio, actualización y finalización.

#### Scenario: Avance de progreso en etapas del pipeline
- **WHEN** un trabajo `pipeline` transita por `ingest`, `transcribe`, `select` y `render`
- **THEN** el estado persistido actualiza `stage` y aumenta `progress` de forma monótona hasta `100` al completar el renderizado

### Requirement: Reintentos con backoff y fallos definitivos
Ante errores recuperables durante la ejecución, el worker SHALL reintentar el trabajo hasta el máximo de intentos configurado aplicando espera creciente (backoff), incrementando `attempts` y registrando el error; al agotar intentos SHALL marcarlo como `failed` y reflejar el fallo en el proyecto asociado.

#### Scenario: Reintento tras fallo transitorio
- **WHEN** un trabajo falla en su primer intento por un error recuperable y tiene intentos disponibles
- **THEN** vuelve a estado `queued` con `attempts` incrementado, una hora programada futura de reejecución y el detalle del error guardado

#### Scenario: Fallo definitivo al agotar intentos
- **WHEN** un trabajo falla alcanzando el límite máximo de intentos
- **THEN** su estado pasa definitivamente a `failed` con el error registrado y no vuelve a ejecutarse automáticamente

### Requirement: Cancelación de trabajos
El sistema SHALL permitir cancelar trabajos en estado `queued` o `running`. Un trabajo `queued` SHALL pasar de inmediato a `cancelled`; un trabajo `running` SHALL interrumpirse en el siguiente punto seguro de control o al detener su subproceso activo y pasar a `cancelled` sin reintentarse.

#### Scenario: Cancelación de un trabajo en cola
- **WHEN** se solicita la cancelación de un trabajo en estado `queued`
- **THEN** su estado cambia inmediatamente a `cancelled` y el worker no lo reclama ni ejecuta

#### Scenario: Cancelación de un trabajo en ejecución
- **WHEN** se solicita la cancelación de un trabajo en estado `running`
- **THEN** el worker detiene la ejecución antes de iniciar nuevas etapas o subprocesos, registra el estado `cancelled` y libera el recurso pesado si estaba retenido

### Requirement: Recuperación de trabajos huérfanos
Al arrancar, el worker SHALL detectar trabajos que quedaron en estado `running` con latido vencido tras una caída previa y SHALL devolverlos a `queued` (o marcarlos `failed` si agotaron intentos) liberando cualquier bloqueo retenido.

#### Scenario: Recuperación automática tras cierre abrupto
- **WHEN** el worker arranca y encuentra un trabajo en `running` cuyo último latido excede el umbral de expiración configurado
- **THEN** el trabajo se devuelve a `queued` con `attempts` incrementado y su bloqueo pesado liberado para ser retomado
