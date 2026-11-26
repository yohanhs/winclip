# Spec Delta

## Purpose

Permite arrancar WinClip en local con un solo comando, centraliza su configuración y diagnostica si las herramientas externas que necesita el pipeline están disponibles y correctamente configuradas.

## ADDED Requirements

### Requirement: Arranque unificado
El sistema SHALL poder iniciarse en desarrollo con un único comando desde la raíz del repo, que levante la API en `API_PORT` y la web en `WEB_PORT`.

#### Scenario: Arranque correcto
- **WHEN** el usuario ejecuta `pnpm dev` en la raíz con las dependencias instaladas
- **THEN** la API responde en `http://localhost:8000/api/health` y la web responde en `http://localhost:3000`

#### Scenario: Una app falla al arrancar
- **WHEN** uno de los dos procesos termina con error
- **THEN** el comando muestra el error con el prefijo de la app que falló y detiene el otro proceso

### Requirement: Configuración centralizada
El backend SHALL leer toda su configuración de variables de entorno o de `.env`, aplicar los valores por defecto documentados en `.env.example` y no requerir ninguna clave de API para arrancar.

#### Scenario: Arranque sin claves LLM
- **WHEN** la API arranca sin `GEMINI_API_KEY`, `NVIDIA_API_KEY`, `OPENROUTER_API_KEY` ni `GROQ_API_KEY`
- **THEN** arranca correctamente y el doctor informa esas claves como "ausente"

#### Scenario: Ruta de ffmpeg personalizada
- **WHEN** `FFMPEG_BIN` apunta a un ejecutable concreto
- **THEN** todas las comprobaciones y usos de ffmpeg emplean esa ruta y no el `ffmpeg` del PATH

#### Scenario: Almacenamiento en disco externo
- **WHEN** `STORAGE_DIR` apunta a una ruta en un volumen externo (como `/Volumes/yohan/Proyectos/winclip/storage`) y `DATABASE_URL` no se especifica
- **THEN** el almacenamiento de media y la base de datos SQLite (`winclip.db`) usan ese directorio, y si el volumen no está montado el doctor devuelve `error` sin crear carpetas locales falsas bajo `/Volumes`

### Requirement: Diagnóstico de dependencias
El sistema SHALL ofrecer un diagnóstico que, para cada dependencia, devuelva nombre, estado (`ok`, `warn` o `error`), detalle legible y sugerencia de corrección. Debe estar disponible por CLI (`winclip doctor`) y por `GET /api/health`.

#### Scenario: Todo correcto
- **WHEN** ffmpeg-full con libass, ffprobe, yt-dlp, el modelo whisper, Ollama, Chromium de Playwright y el almacenamiento están disponibles
- **THEN** cada check es `ok` y `winclip doctor` termina con código 0

#### Scenario: ffmpeg sin libass
- **WHEN** `FFMPEG_BIN` apunta a un ffmpeg sin el filtro `ass`
- **THEN** el check de ffmpeg es `error` y sugiere instalar `ffmpeg-full`, y `winclip doctor` termina con código distinto de 0

#### Scenario: Servicio opcional caído
- **WHEN** Ollama no responde o el disco `/Volumes/yohan` no está montado
- **THEN** el check correspondiente es `warn` (no `error`) y el código de salida no se ve afectado

#### Scenario: Secretos nunca expuestos
- **WHEN** se consulta el diagnóstico con claves configuradas
- **THEN** la respuesta solo indica "presente" o "ausente" por clave y nunca incluye su valor ni un fragmento

### Requirement: Página de estado del sistema
La web SHALL mostrar el resultado del diagnóstico con un indicador por check y la sugerencia de corrección cuando no sea `ok`, y SHALL ofrecer navegación a las secciones Proyectos, Campañas, Cuentas, Publicaciones y Ajustes.

#### Scenario: API disponible
- **WHEN** el usuario abre la página de estado con la API en marcha
- **THEN** ve la lista de checks con su estado y detalle

#### Scenario: API no disponible
- **WHEN** la API no responde
- **THEN** la página muestra un aviso claro de "API no disponible" con el comando para arrancarla, sin romper la navegación
