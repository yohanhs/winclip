# Tasks

## 1. Almacenamiento cifrado, modelo de datos y dependencias

- [x] 1.1 Añadir `cryptography`, `keyring`, `google-auth`, `google-auth-oauthlib`, `google-api-python-client` y `playwright` a `apps/api/pyproject.toml`, añadir `WINCLIP_SECRET_KEY` (opcional) en `winclip/core/config.py` y `.env.example`, y verificar con `uv sync --project apps/api && uv run --project apps/api python -c "import cryptography, keyring, googleapiclient, playwright"`.
- [x] 1.2 Implementar `winclip/accounts/crypto.py` con resolución de clave maestra (`WINCLIP_SECRET_KEY` → macOS Keychain vía `keyring`), cifrado/descifrado Fernet atómico de `storage/accounts/<account_id>/credentials.enc` (permisos `0600`) y borrado seguro de directorio de cuenta. Verificar con `uv run --project apps/api pytest tests/test_accounts_crypto.py` (ida y vuelta cifrada, permisos de archivo, error controlado ante clave distinta y no escritura en claro).
- [x] 1.3 Añadir/ampliar el modelo SQLModel `SocialAccount` en `winclip/core/models.py` (con `alias`, `avatar_url`, `is_default`, `capabilities_json`, `external_account_id`, `token_expires_at`, `last_error`) y helper transaccional para garantizar una única cuenta por defecto por `(workspace_id, platform)`. Verificar con `uv run --project apps/api pytest tests/test_accounts_model.py`.

## 2. Flujos OAuth oficiales, refresco, salud e importación

- [x] 2.1 Implementar `winclip/accounts/oauth.py` con gestor de estado OAuth anti-CSRF (TTL + PKCE) y flujos completos para YouTube (`GOOGLE_CLIENT_SECRET_FILE`, scopes `youtube.upload`, `youtube.readonly`, `youtube.force-ssl`), TikTok (detección de `video.publish` vs modo inbox `video.upload`) e Instagram Graph (long-lived token y descubrimiento/selección de cuentas Business/Creator vinculadas a página de Facebook). Verificar con `uv run --project apps/api pytest tests/test_accounts_oauth.py` usando respuestas HTTP simuladas para los 3 proveedores y validación de state inválido.
- [x] 2.2 Implementar `winclip/accounts/health.py` con refresco automático de tokens OAuth (YouTube, TikTok e Instagram) y `check_account` actualizando `display_name`, `handle`, `avatar_url`, `status`, `token_expires_at` y `last_check_at`. Verificar con tests en `tests/test_accounts_health.py` cubriendo token vigente, token expirado con refresco exitoso y token revocado (`expired`/`error`).
- [x] 2.3 Implementar `winclip/accounts/importer.py` para importar tokens existentes desde una ruta local (archivo individual o carpeta `tokens/*.json` en modo solo lectura, detectando formato Google Authorized User y TikTok) sin copiar ni modificar el archivo fuente. Verificar con `uv run --project apps/api pytest tests/test_accounts_importer.py` comprobando que el archivo origen no se altera y que las credenciales se cifran en `storage/accounts/<id>/credentials.enc`.

## 3. Sesión persistente Playwright, API REST, CLI y doctor

- [x] 3.1 Implementar `winclip/publishers/playwright/session.py` y `winclip/accounts/browser_login.py` para lanzar Chromium visible con perfil persistente en `storage/accounts/<id>/profile`, lock por cuenta, detección de login (cookies/URL + confirmación manual), timeout/cancelación y health check de sesión persistente. Verificar con tests en `tests/test_browser_login.py` usando contexto Playwright simulado y prueba manual abriendo ventana visible en local.
- [x] 3.2 Implementar `winclip/routers/accounts.py` con todos los endpoints (`/api/accounts`, `PATCH`/`DELETE`, `POST /{id}/check`, `oauth/{platform}/start|callback`, `oauth/instagram/select`, `browser-login/start|status|confirm|cancel`, `import`), asegurando sanitización de logs y respuestas sin secretos, y registrarlo en `winclip/main.py`. Verificar con `uv run --project apps/api pytest tests/test_accounts_api.py` incluyendo un test que inspecciona respuestas y logs para asegurar cero fugas de tokens/secretos.
- [x] 3.3 Añadir subcomandos `winclip accounts list|check|import` en `winclip/cli.py`, añadir checks informativos de credenciales sociales y backend de cifrado en `winclip/core/doctor.py` (sin revelar secretos), documentar la configuración OAuth (YouTube, TikTok, Meta) e importación de tokens en `README.md`, y regenerar `packages/api-client`. Verificar con `uv run --project apps/api winclip doctor` y tests de CLI/doctor.

## 4. Interfaz web de cuentas (`/accounts`)

- [x] 4.1 Implementar la página `/accounts` en `apps/web` agrupada por plataforma (YouTube, TikTok, Instagram) con tarjetas por cuenta mostrando avatar, nombre, handle, alias, badge de método (`API`/`Navegador`), badge de estado, indicador "Por defecto", capacidades (p. ej. "Solo inbox") y última verificación. Verificar con `pnpm --filter web lint && pnpm --filter web build`.
- [x] 4.2 Implementar las acciones sobre tarjetas (renombrar alias, marcar por defecto, probar conexión en vivo, reconectar y eliminar con diálogo de confirmación) y el diálogo "Añadir cuenta" (OAuth con guía si faltan variables de entorno, selector multi-cuenta para Instagram, "Conectar con navegador" con estado en vivo + botón confirmar/cancelar, e "Importar token existente" por ruta local). Verificar manualmente contra la API local probando conexión/importación, health check, alias y borrado.

## 5. Verificación integrada

- [x] 5.1 Ejecutar `uv run --project apps/api ruff check . && uv run --project apps/api ruff format --check . && uv run --project apps/api pytest`, `pnpm --filter web lint && pnpm --filter web build`, `uv run --project apps/api winclip doctor`, comprobar `pre-commit run gitleaks --all-files` y ejecutar `openspec validate add-social-accounts --strict` sin errores.

## Workflow follow-up

- Revisión del orquestador y del usuario (y prueba real de OAuth / importación de token HookVault con confirmación del usuario).
- Archivar el change con `openspec archive add-social-accounts` tras la aprobación.
