# subtitle-rendering Specification

## Purpose
Convierte las marcas temporales por palabra de la transcripción en subtítulos karaoke sincronizados al clip, aplicando presets visuales configurables, fuentes con licencia libre o locales y posicionamiento seguro para video vertical.

## Requirements

### Requirement: Re-temporización y agrupación en líneas karaoke
El sistema SHALL filtrar las palabras de `transcript.json` que caen dentro del intervalo `[start, end]` del candidato, re-temporizarlas respecto al segundo `0.0` del clip y agruparlas en bloques de 1 a 2 líneas respetando puntuación, límite de caracteres y límite de palabras del preset.

#### Scenario: Re-temporización exacta al inicio del clip
- **WHEN** un candidato abarca de `812.4` s a `861.0` s y una palabra tiene marcas `813.0`–`813.4` s
- **THEN** el subtítulo coloca esa palabra en `0.60`–`1.00` s relativa al clip sin desfase respecto al audio

#### Scenario: Corte de línea por puntuación y límites
- **WHEN** un segmento contiene una frase larga de 14 palabras con una coma o punto intermedio y el preset limita a 38 caracteres o 7 palabras
- **THEN** las palabras se dividen en múltiples bloques consecutivos de máximo 2 líneas sin cortar palabras a la mitad

#### Scenario: Clip sin palabras transcritas
- **WHEN** el intervalo del candidato no contiene ninguna palabra en `transcript.json`
- **THEN** el sistema genera un archivo `subs.ass` válido sin eventos de diálogo y completa el renderizado sin errores

### Requirement: Resaltado palabra por palabra y zona segura vertical
El sistema SHALL resaltar únicamente la palabra activa en cada instante mediante color destacado y un leve efecto de escala, aplicar mayúsculas cuando el preset lo indique y ubicar los subtítulos dentro de la zona segura vertical (`0.62` a `0.70` de la altura) con márgenes laterales.

#### Scenario: Palabra activa destacada
- **WHEN** un bloque contiene tres palabras consecutivas
- **THEN** durante el intervalo de cada palabra solo esa palabra muestra el color de resaltado y el ligero aumento de tamaño mientras el resto conserva el estilo base

#### Scenario: Posicionamiento sobre la interfaz de redes verticales
- **WHEN** se generan subtítulos para salida `1080x1920` con el preset por defecto
- **THEN** el bloque de subtítulos se posiciona dentro del rango vertical `0.62 H`–`0.70 H` con márgenes horizontales suficientes para no solaparse con los botones de Shorts, Reels o TikTok

#### Scenario: Punto de extensión para emojis
- **WHEN** el modelo de bloques de subtítulos se procesa antes de generar la salida visual
- **THEN** el flujo contempla un campo opcional de enriquecimiento (como emojis asociados al bloque o palabra) que preserva compatibilidad sin requerir generación automática de emojis en este change

### Requirement: Motor ASS por defecto
El sistema SHALL generar un archivo `subs.ass` determinista en el motor por defecto (`ass`) y quemarlo sobre el video utilizando el binario configurado en `FFMPEG_BIN` con acceso a los directorios de fuentes correspondientes.

#### Scenario: Generación determinista de archivo ASS
- **WHEN** se genera `subs.ass` dos veces con los mismos datos de transcripción, rango del clip y preset
- **THEN** ambos archivos resultan idénticos byte a byte y coinciden con el formato esperado para el preset

### Requirement: Motor PIL alternativo
El sistema SHALL ofrecer el motor alternativo `pil` que renderiza los subtítulos karaoke con estilo equivalente (color base, borde, sombra, palabra activa resaltada y zona segura) y los compone sobre el video sin depender del renderizador de subtítulos de ffmpeg.

#### Scenario: Renderizado con motor alternativo pil
- **WHEN** el usuario ejecuta el renderizado con `--engine pil` y el preset `bold-yellow`
- **THEN** el clip resultante incluye subtítulos karaoke visibles en zona segura con la palabra activa en amarillo y también guarda el archivo `subs.ass` correspondiente

### Requirement: Presets configurables y resolución de fuentes
El sistema SHALL distribuir en `assets/subtitle-presets/` al menos los presets `bold-yellow`, `hormozi`, `clean-white` y `mrbeast`, cargar fuentes OFL desde `assets/fonts/` y permitir fuentes comerciales locales desde `USER_FONTS_DIR` con respaldo automático a una fuente OFL si la fuente solicitada no existe.

#### Scenario: Selección de preset incorporado
- **WHEN** se especifica `--preset hormozi` o cualquier otro preset presente en `assets/subtitle-presets/`
- **THEN** el sistema valida su esquema JSON y aplica sus parámetros de tipografía, colores, contorno, mayúsculas y agrupación

#### Scenario: Fuente comercial local presente o ausente
- **WHEN** se solicita una fuente comercial local (por ejemplo `GothamBlack`) y el archivo no existe en `USER_FONTS_DIR`
- **THEN** el sistema emite una advertencia, recurre automáticamente a la fuente OFL de respaldo del preset y registra la fuente efectivamente usada en `render.json`

#### Scenario: Preset inexistente
- **WHEN** el usuario indica un nombre de preset que no existe en `assets/subtitle-presets/`
- **THEN** el sistema falla antes de renderizar listando los presets disponibles
