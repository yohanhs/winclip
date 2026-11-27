# Spec Delta

## Purpose

Permite conectar, cifrar en reposo, refrescar, diagnosticar y administrar múltiples cuentas de YouTube, TikTok e Instagram por workspace, soportando tanto autenticación oficial por API (OAuth) como sesiones persistentes de navegador con login manual.

## ADDED Requirements

### Requirement: Múltiples cuentas, alias y cuenta por defecto por plataforma
El sistema SHALL permitir registrar y gestionar múltiples cuentas independientes por cada plataforma soportada (`youtube`, `tiktok`, `instagram`), asignando a cada una un alias editable y permitiendo designar como máximo una cuenta por defecto por plataforma dentro del workspace.

#### Scenario: Registro de varias cuentas en la misma plataforma
- **WHEN** el usuario conecta dos canales distintos de YouTube en el mismo workspace
- **THEN** ambas cuentas coexisten con identificadores, credenciales y estados independientes y pueden distinguirse por su nombre, handle y alias

#### Scenario: Cambio de cuenta por defecto
- **WHEN** el usuario marca una segunda cuenta de TikTok como cuenta por defecto de esa plataforma
- **THEN** la nueva cuenta pasa a ser la cuenta por defecto y la anterior pierde automáticamente esa marca

### Requirement: Conexión de cuentas mediante OAuth oficial
El sistema SHALL ofrecer flujos de autenticación OAuth para YouTube, TikTok e Instagram (cuentas Business o Creator vinculadas a una página de Facebook), validando protección anti-CSRF en el callback y registrando los permisos efectivamente concedidos por cada plataforma.

#### Scenario: Conexión OAuth de YouTube
- **WHEN** el usuario inicia la conexión API de YouTube con credenciales de cliente configuradas y autoriza los permisos solicitados
- **THEN** el sistema intercambia el código, obtiene nombre, handle y avatar del canal y guarda la cuenta en estado conectado

#### Scenario: Conexión OAuth de TikTok sin publicación directa aprobada
- **WHEN** el usuario completa la autorización OAuth de TikTok con permiso de carga pero sin permiso de publicación directa
- **THEN** el sistema conecta la cuenta correctamente y registra que opera en modo borrador (inbox)

#### Scenario: Selección entre varias cuentas de Instagram vinculadas
- **WHEN** el usuario autoriza una sesión de Meta con acceso a dos cuentas Business o Creator de Instagram
- **THEN** el sistema lista las cuentas elegibles y permite elegir cuál o cuáles registrar en WinClip

#### Scenario: Credenciales de aplicación faltantes
- **WHEN** el usuario intenta iniciar un flujo OAuth sin haber configurado las variables de entorno requeridas para esa plataforma
- **THEN** el sistema rechaza el inicio con un mensaje claro indicando qué configuración falta, sin revelar secretos

### Requirement: Conexión interactiva con navegador persistente
El sistema SHALL permitir conectar cuentas de TikTok e Instagram abriendo un navegador visible con un perfil persistente aislado por cuenta para que el usuario realice el inicio de sesión y cualquier verificación 2FA de forma manual.

#### Scenario: Inicio de sesión manual exitoso en navegador
- **WHEN** el usuario pulsa "Conectar con navegador" para una cuenta y completa el inicio de sesión en la ventana visible
- **THEN** el sistema detecta la sesión autenticada, persiste el perfil aislado de esa cuenta, cierra la ventana y marca la cuenta como conectada

#### Scenario: Cancelación o expiración del tiempo de login
- **WHEN** el usuario cierra el navegador o vence el tiempo límite sin completar el inicio de sesión
- **THEN** el sistema no marca la cuenta como conectada e informa el estado pendiente o cancelado sin corromper otros perfiles

### Requirement: Almacenamiento cifrado y protección de secretos
El sistema MUST almacenar todas las credenciales OAuth cifradas en disco fuera de la base de datos y del repositorio, y MUST evitar la exposición de tokens, secretos de cliente o claves de cifrado en respuestas de API, logs y diagnósticos del sistema.

#### Scenario: Inspección de credenciales en disco y respuestas API
- **WHEN** una cuenta OAuth queda conectada y se consulta su detalle por API o se revisan los archivos en almacenamiento local
- **THEN** las credenciales en disco están cifradas (no en texto plano) y la respuesta API nunca incluye tokens ni secretos

#### Scenario: Eliminación de cuenta y limpieza de artefactos locales
- **WHEN** el usuario elimina una cuenta conectada (API o navegador)
- **THEN** el sistema elimina el registro y borra el directorio de credenciales o perfil persistente asociado a esa cuenta en disco

### Requirement: Refresco de tokens y comprobación de salud
El sistema SHALL refrescar automáticamente tokens OAuth próximos a expirar o expirados cuando exista un token de refresco válido, y SHALL permitir ejecutar una comprobación de salud por cuenta que actualice nombre, avatar, estado y fecha de última verificación.

#### Scenario: Refresco transparente durante verificación de salud
- **WHEN** se ejecuta la comprobación de salud sobre una cuenta OAuth cuyo token de acceso expiró pero tiene token de refresco válido
- **THEN** el sistema renueva el token cifrado en disco, consulta el perfil y devuelve estado `connected` con los datos actualizados

#### Scenario: Credenciales revocadas o sesión expirada
- **WHEN** la plataforma rechaza la credencial o la sesión de navegador ya no está autenticada durante la comprobación de salud
- **THEN** el sistema marca la cuenta como `expired` o `error` con un motivo comprensible y habilita la reconexión

### Requirement: Importación opcional de tokens locales existentes
El sistema SHALL permitir importar credenciales de cuentas existentes desde una ruta local indicada por el usuario en modo solo lectura, cifrándolas en el almacenamiento interno sin copiar ni modificar los archivos originales.

#### Scenario: Importación de token local de YouTube
- **WHEN** el usuario indica una ruta local válida a un archivo de token autorizado existente
- **THEN** el sistema lee las credenciales, las guarda cifradas bajo una nueva cuenta, valida el canal remoto y mantiene intacto el archivo original fuera del repositorio

#### Scenario: Ruta inexistente o formato inválido
- **WHEN** el usuario proporciona una ruta que no existe o un archivo que no corresponde a un token soportado
- **THEN** el sistema rechaza la importación con un error claro y no crea registros huérfanos

### Requirement: Interfaz web de administración de cuentas
La interfaz web SHALL ofrecer una página `/accounts` agrupada por plataforma que muestre las tarjetas de cada cuenta con su estado, avatar, alias y método de autenticación, y permita añadir, importar, renombrar, marcar como predeterminada, probar conexión, reconectar y eliminar cuentas.

#### Scenario: Gestión diaria desde `/accounts`
- **WHEN** el usuario abre `/accounts` con cuentas conectadas en varias plataformas
- **THEN** ve las tarjetas agrupadas por plataforma con acciones funcionales para renombrar alias, cambiar la cuenta por defecto, ejecutar una prueba de conexión en vivo, reconectar o eliminar con confirmación
