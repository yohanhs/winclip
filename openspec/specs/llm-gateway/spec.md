# llm-gateway Specification

## Purpose
Centraliza las invocaciones a proveedores LLM gratuitos con enrutamiento por prioridad, tolerancia a límites de tasa y fallos, validación estricta de respuestas JSON y caché determinista en disco.

## Requirements

### Requirement: Enrutamiento por orden configurado
El sistema SHALL intentar los proveedores LLM en el orden definido por `LLM_PROVIDER_ORDER` y SHALL omitir automáticamente aquellos que carezcan de credenciales o no estén disponibles en el entorno.

#### Scenario: Omisión de proveedor sin clave
- **WHEN** `LLM_PROVIDER_ORDER` lista primero un proveedor sin clave configurada y segundo uno con clave válida
- **THEN** el gateway omite el primero sin generar error fatal, invoca al segundo y devuelve su respuesta

#### Scenario: Ningún proveedor disponible
- **WHEN** ningún proveedor listado en `LLM_PROVIDER_ORDER` tiene credenciales ni servicio accesible
- **THEN** la solicitud falla con un error descriptivo que resume el motivo por proveedor y nunca expone valores de claves

### Requirement: Tolerancia a 429, errores 5xx y timeouts
Ante límites de tasa (HTTP 429), errores de servidor (5xx) o expiración del timeout configurado, el sistema SHALL reintentar con espera exponencial acotada y, si el fallo persiste, SHALL hacer fallback al siguiente proveedor disponible.

#### Scenario: Fallback tras 429 persistente
- **WHEN** el primer proveedor responde con HTTP 429 en todos sus intentos configurados
- **THEN** el gateway espera con backoff entre reintentos, luego delega la petición al siguiente proveedor disponible y devuelve la respuesta exitosa

#### Scenario: Fallback por timeout o error 5xx
- **WHEN** un proveedor excede el timeout configurado o devuelve HTTP 503 de forma persistente
- **THEN** el gateway avanza al siguiente proveedor disponible en `LLM_PROVIDER_ORDER` hasta obtener una respuesta válida o agotar la lista

### Requirement: Salida JSON validada con autocorrección
El sistema SHALL exigir que toda respuesta cumpla el esquema JSON solicitado; si el proveedor devuelve texto no parseable o con errores de esquema, SHALL reintentar en ese proveedor enviando un mensaje de corrección antes de hacer fallback al siguiente.

#### Scenario: Corrección exitosa en reintento
- **WHEN** un proveedor devuelve JSON malformado o con campos faltantes en el primer intento y responde JSON válido tras recibir el error de validación
- **THEN** el gateway acepta la respuesta corregida y la devuelve ya validada

#### Scenario: Fallo persistente de esquema
- **WHEN** un proveedor sigue devolviendo respuestas inválidas tras agotar los reintentos de corrección
- **THEN** el gateway descarta ese proveedor para la solicitud actual y pasa al siguiente proveedor disponible

### Requirement: Caché determinista en disco
El sistema SHALL almacenar cada respuesta JSON validada en `STORAGE_DIR/cache/llm/<sha256>.json`, calculando el hash SHA-256 sobre el prompt, el esquema solicitado y el modelo lógico, y SHALL reutilizar la caché en solicitudes idénticas salvo que se desactive explícitamente.

#### Scenario: Reutilización de respuesta cacheada
- **WHEN** se realiza una segunda solicitud con el mismo prompt, esquema y modelo lógico
- **THEN** el gateway devuelve el resultado desde `STORAGE_DIR/cache/llm/<sha256>.json` sin realizar llamadas externas y marca la respuesta como proveniente de caché

#### Scenario: Invalidación al cambiar entrada
- **WHEN** cambia el contenido del prompt, el esquema o el modelo lógico
- **THEN** se calcula un hash distinto y se ejecuta una nueva llamada al enrutador

### Requirement: Trazabilidad de ejecución sin fuga de secretos
Cada respuesta completada SHALL informar el proveedor y modelo concreto que respondió, si provino de caché y el conteo aproximado de tokens de entrada y salida, sin escribir nunca claves de API en logs ni en archivos de caché.

#### Scenario: Metadatos de proveedor y consumo
- **WHEN** una solicitud finaliza correctamente
- **THEN** el resultado incluye `provider`, `model`, `cached` y tokens aproximados de entrada y salida, y ni los logs ni el archivo de caché contienen ninguna clave de API

### Requirement: Comando de verificación de conectividad LLM
El sistema SHALL proveer el comando `winclip llm test` para ejecutar una solicitud JSON mínima a través del enrutador y mostrar el proveedor y modelo que respondió junto con el resumen de intentos.

#### Scenario: Verificación exitosa
- **WHEN** el usuario ejecuta `winclip llm test` y al menos un proveedor configurado responde con el JSON esperado
- **THEN** el comando muestra el proveedor y modelo activos, la latencia y termina con código de salida 0

#### Scenario: Todos los proveedores fallan
- **WHEN** el usuario ejecuta `winclip llm test` y ningún proveedor logra responder con éxito
- **THEN** el comando muestra el motivo de fallo de cada proveedor intentado y termina con código distinto de 0
