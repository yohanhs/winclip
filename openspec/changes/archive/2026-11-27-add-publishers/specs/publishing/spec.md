# Spec Delta

## Purpose

Permite publicar y programar clips renderizados en múltiples cuentas de YouTube, TikTok e Instagram con metadatos adaptados y editables, control de cuotas, idempotencia, reintentos y trazabilidad completa en una cola local.

## ADDED Requirements

### Requirement: Publicación en YouTube Shorts vía API oficial
El sistema SHALL publicar clips en cuentas API de YouTube enviando el video junto con título (máximo 100 caracteres), descripción, etiquetas, categoría, idioma y privacidad, soportando programación nativa por fecha futura, subida de miniatura, comentario inicial y aviso visible sobre la cuota diaria estimada.

#### Scenario: Publicación inmediata con miniatura y comentario
- **WHEN** se publica un clip renderizado en una cuenta API de YouTube con metadatos válidos, miniatura y comentario configurados
- **THEN** el sistema sube el video, aplica la miniatura, publica el comentario asociado, guarda el identificador y enlace externo y marca la publicación como `published`

#### Scenario: Programación nativa en YouTube
- **WHEN** el usuario programa un clip para una fecha futura en una cuenta API de YouTube
- **THEN** el sistema sube el video en modo privado con la fecha de publicación programada en YouTube, guarda el identificador externo y registra la publicación como `scheduled`

#### Scenario: Título demasiado largo o cuota diaria agotada
- **WHEN** el título supera 100 caracteres al validar metadatos o la plataforma responde que se agotó la cuota diaria
- **THEN** el sistema rechaza títulos inválidos antes de subir y, ante cuota agotada, marca la publicación como `failed` sin reintentos automáticos ciegos mostrando un aviso de límite diario

### Requirement: Publicación en TikTok vía API oficial
El sistema SHALL publicar clips en cuentas API de TikTok usando publicación directa cuando la cuenta dispone del permiso correspondiente o enviándolos como borrador al inbox con aviso explícito en caso contrario, consultando el estado remoto hasta obtener un resultado definitivo.

#### Scenario: Publicación directa aprobada
- **WHEN** se publica un clip en una cuenta API de TikTok con permiso de publicación directa
- **THEN** el sistema sube el video, espera la confirmación final del estado remoto y registra el resultado como `published`

#### Scenario: Degradación a borrador inbox
- **WHEN** se publica un clip en una cuenta API de TikTok sin permiso de publicación directa
- **THEN** el sistema envía el video al inbox de TikTok, verifica la recepción y registra la publicación con un aviso claro indicando que debe completarse desde la app de TikTok

### Requirement: Publicación en Instagram Reels vía API oficial desde almacenamiento local
El sistema SHALL publicar clips locales como Reels en cuentas API de Instagram sin requerir que WinClip exponga un servidor público ni suba archivos a almacenamiento externo de terceros, esperando a que el contenedor remoto termine su procesamiento antes de publicarlo.

#### Scenario: Publicación de Reel desde archivo local
- **WHEN** se publica un clip renderizado en una cuenta API de Instagram Business o Creator
- **THEN** el sistema transfiere el archivo binario local mediante subida reanudable oficial, comprueba que el procesamiento remoto finalizó, publica el Reel y guarda su identificador y enlace externo

### Requirement: Publicación por navegador visible como respaldo
El sistema SHALL ofrecer publicación mediante navegador automatizado visible para cuentas de TikTok e Instagram conectadas por sesión de navegador, usando pausas naturales, guardando capturas en cada paso y deteniéndose de inmediato si detecta sesión expirada o un desafío anti-bot o de verificación.

#### Scenario: Publicación con capturas por paso
- **WHEN** se ejecuta una publicación sobre una cuenta de TikTok o Instagram configurada con sesión de navegador
- **THEN** el sistema abre el navegador visible con el perfil aislado de esa cuenta, realiza la carga con pausas entre acciones, guarda capturas de los pasos y actualiza el historial al finalizar

#### Scenario: Detección de desafío anti-bot o sesión expirada
- **WHEN** durante la publicación por navegador aparece un desafío de verificación humana, solicitud 2FA o redirección a inicio de sesión
- **THEN** el sistema detiene el flujo sin intentar resolver el desafío, guarda una captura del error, marca la publicación como `failed` sin reintentos automáticos y muestra la captura al usuario

### Requirement: Cola multi-clip, programación, idempotencia y límites diarios
El sistema SHALL procesar cada combinación `(clip × cuenta)` como un trabajo independiente en la cola local, respetando programación diferida para plataformas sin programación nativa, evitando subidas duplicadas mediante `external_id`, reintentando solo errores transitorios y aplicando límites diarios por cuenta.

#### Scenario: Encolado matricial de varios clips en varias cuentas
- **WHEN** el usuario confirma publicar 2 clips seleccionados en 3 cuentas distintas
- **THEN** el sistema crea 6 registros de publicación y 6 trabajos independientes con progreso en tiempo real por cada par `(clip, cuenta)`

#### Scenario: Programación diferida en TikTok o Instagram
- **WHEN** el usuario programa una publicación futura para TikTok o Instagram
- **THEN** el registro queda en estado `scheduled` y el worker dispara la subida al alcanzar la fecha programada, pudiendo cancelarse antes de ejecutarse

#### Scenario: Idempotencia ante reintento con video ya subido
- **WHEN** una publicación falla después de haber recibido un `external_id` válido y el usuario solicita reintentarla
- **THEN** el sistema no sube un segundo video duplicado y solo reintenta pasos secundarios pendientes o reconcilia el estado final

#### Scenario: Límite diario por cuenta alcanzado
- **WHEN** se intenta encolar o ejecutar una publicación en una cuenta que ya alcanzó su límite diario configurado
- **THEN** el sistema advierte al usuario y evita superar el límite sin autorización explícita

### Requirement: Metadatos por plataforma y diálogo de publicación
El sistema SHALL precalcular metadatos específicos por plataforma combinando el clip y su campaña asociada, y SHALL permitir editarlos antes de confirmar desde un diálogo "Publicar" con multi-selección de clips y cuentas agrupadas por plataforma.

#### Scenario: Prellenado y edición previa en el diálogo Publicar
- **WHEN** el usuario selecciona uno o más clips renderizados y abre el diálogo "Publicar"
- **THEN** el sistema muestra las cuentas conectadas agrupadas por plataforma, precarga título, descripción, hashtags, CTA y opciones según cada red y permite editar cada campo y elegir publicación inmediata o programada antes de confirmar

### Requirement: Historial y control de publicaciones en la web
La interfaz web SHALL ofrecer una página `/publications` que muestre el historial filtrable de publicaciones con estado en tiempo real, enlace externo cuando esté publicado, detalle de error con captura de pantalla cuando exista y acciones para reintentar fallidas o cancelar programadas.

#### Scenario: Inspección de fallo y reintento desde `/publications`
- **WHEN** una publicación falla y cuenta con mensaje de error y captura de pantalla
- **THEN** el usuario visualiza el estado `failed`, puede abrir la captura en `/publications` y lanzar un reintento manual que encola un nuevo intento

#### Scenario: Cancelación de publicación programada
- **WHEN** el usuario cancela una publicación en estado `scheduled` desde `/publications`
- **THEN** el sistema cancela el trabajo pendiente y actualiza su estado para impedir que se publique
