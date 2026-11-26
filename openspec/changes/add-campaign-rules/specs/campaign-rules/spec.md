# Spec Delta

## Purpose

Permite definir, validar, parsear desde briefs en texto libre y reutilizar campañas de clipping con reglas editoriales y visuales, aplicándolas automáticamente a la selección de momentos, la detección de incumplimientos y el renderizado de cada clip.

## ADDED Requirements

### Requirement: Esquema y validación de reglas de campaña
El sistema SHALL validar toda campaña contra un esquema estructurado que incluya nombre, idioma (`es`, `en` o `auto`), duraciones mínima y máxima, máximo de clips, temas prioritarios y prohibidos, palabras prohibidas, palabras clave obligatorias, tono, duración máxima del hook, texto CTA, hashtags, preset de subtítulos, marca de agua, plataformas objetivo e instrucciones extra.

#### Scenario: Rangos de duración válidos
- **WHEN** el usuario crea o actualiza una campaña con `min_duration` igual a 20 y `max_duration` igual a 60
- **THEN** el sistema acepta la campaña y persiste las reglas normalizadas

#### Scenario: Duración fuera de rango o invertida
- **WHEN** el usuario envía una campaña con `min_duration` menor a 5, `max_duration` mayor a 180 o `min_duration` mayor o igual que `max_duration`
- **THEN** el sistema rechaza la operación con un error de validación indicando el campo afectado

#### Scenario: Referencia inválida de preset o marca de agua
- **WHEN** el usuario indica un `subtitle_preset` inexistente o una ruta de `watermark_path` fuera del almacenamiento gestionado
- **THEN** el sistema rechaza la campaña con un error de validación descriptivo

### Requirement: Gestión CRUD y duplicación de campañas
El sistema SHALL permitir listar, consultar, crear, editar, duplicar y eliminar campañas dentro del workspace activo, preservando los proyectos históricos si una campaña se elimina.

#### Scenario: Duplicación de campaña existente
- **WHEN** el usuario solicita duplicar una campaña existente
- **THEN** el sistema crea una nueva campaña independiente con todas sus reglas y texto fuente copiados y un nombre distinguible

#### Scenario: Eliminación de campaña referenciada por proyectos
- **WHEN** el usuario elimina una campaña asociada a proyectos anteriores
- **THEN** la campaña se elimina, los proyectos conservan sus clips y su referencia a campaña queda vacía

### Requirement: Parseo asistido de briefs en texto libre
El sistema SHALL ofrecer una operación que reciba un brief en texto libre en español o inglés y devuelva una propuesta de reglas estructuradas junto con la lista explícita de campos inferidos, sin guardar la campaña hasta que el usuario la confirme.

#### Scenario: Brief parcial en español o inglés
- **WHEN** el usuario envía un brief que especifica duración, hashtags y prohibiciones pero omite tono y preset de subtítulos
- **THEN** el sistema devuelve una propuesta válida con los valores extraídos del texto, valores sugeridos para los campos omitidos y marca los campos omitidos dentro de `inferred_fields`

#### Scenario: Edición previa al guardado
- **WHEN** el usuario revisa la propuesta devuelta por el análisis de brief y modifica uno o más campos antes de confirmar
- **THEN** la campaña solo se persiste cuando el usuario confirma el guardado y almacena los valores editados junto con el brief original en `source_text`

#### Scenario: Fallo de proveedores de análisis
- **WHEN** ningún proveedor de lenguaje responde correctamente al analizar un brief
- **THEN** el sistema informa un error recuperable y permite completar el formulario manualmente sin perder el texto pegado

### Requirement: Plantillas de ejemplo para campañas de clipping
El sistema SHALL proveer plantillas predefinidas en español e inglés inspiradas en campañas reales de clipping que incluyan duración, menciones obligatorias, hashtags, restricciones y CTA para acelerar la creación de campañas.

#### Scenario: Carga de plantilla en el editor
- **WHEN** el usuario consulta las plantillas disponibles y selecciona una plantilla en español o inglés
- **THEN** el editor precarga todas las reglas de esa plantilla listas para personalizar y guardar como campaña nueva

### Requirement: Integración con la creación y selección de clips
El sistema SHALL habilitar la selección de campaña al crear un proyecto y MUST aplicar las reglas de la campaña durante la selección de candidatos y la verificación posterior de incumplimientos.

#### Scenario: Selección de campaña en nuevo proyecto
- **WHEN** el usuario crea un proyecto en `/projects/new` eligiendo una campaña activa
- **THEN** el proyecto queda vinculado a esa campaña, hereda por defecto sus parámetros compatibles y el proceso de selección recibe todas sus reglas

#### Scenario: Registro de incumplimientos por clip
- **WHEN** un candidato seleccionado incumple reglas verificables de la campaña (como duración fuera de rango, presencia de una palabra prohibida o ausencia de una palabra clave o hashtag obligatorio)
- **THEN** el sistema registra cada incumplimiento en `rule_violations` del candidato y del clip generado

### Requirement: Aplicación de reglas de campaña al renderizado
El sistema SHALL aplicar al renderizado de cada clip las reglas visuales configuradas en la campaña asociada: preset de subtítulos, marca de agua, texto CTA y duración máxima del overlay de hook.

#### Scenario: Renderizado con reglas visuales de campaña
- **WHEN** se renderiza un clip perteneciente a un proyecto con campaña que define `subtitle_preset`, `watermark_path`, `cta_text` y `hook_max_seconds`
- **THEN** el video final usa ese preset de subtítulos, incorpora la marca de agua en zona segura, muestra el CTA configurado y limita el overlay de hook a `hook_max_seconds`

#### Scenario: Proyecto sin campaña
- **WHEN** se renderiza un clip de un proyecto sin campaña asociada
- **THEN** el sistema aplica los valores predeterminados sin marca de agua ni restricciones adicionales

### Requirement: Interfaz web de gestión de campañas y alertas en clips
La interfaz web SHALL ofrecer una sección `/campaigns` con lista, editor estructurado, pestaña "Pegar brief" con marca visual de campos inferidos y vista previa JSON sincronizada, y SHALL mostrar los `rule_violations` de cada clip en su tarjeta de revisión.

#### Scenario: Revisión de brief y vista previa JSON
- **WHEN** el usuario analiza un brief en la pestaña "Pegar brief" de `/campaigns`
- **THEN** la interfaz muestra la propuesta en el editor estructurado resaltando los campos inferidos y actualiza en vivo la vista previa JSON con cualquier edición

#### Scenario: Visualización de incumplimientos en tarjeta de clip
- **WHEN** el usuario revisa un proyecto cuyos clips tienen uno o más elementos en `rule_violations`
- **THEN** cada tarjeta afectada muestra indicadores claros con el detalle de cada incumplimiento sin bloquear la reproducción ni la edición del clip
