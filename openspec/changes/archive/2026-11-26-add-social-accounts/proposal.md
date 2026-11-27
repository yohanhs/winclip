# Proposal

## Why

El usuario gestiona múltiples canales y cuentas (por ejemplo HookVault en YouTube y TikTok, más futuras cuentas adicionales en YouTube, TikTok e Instagram) y necesita decidir a qué cuentas concretas enviar cada short sin repetir scripts ni exponer tokens en el repositorio público. Antes de construir los publicadores automáticos hace falta un gestor de cuentas sociales seguro que conecte varias cuentas por plataforma mediante OAuth oficial o sesión de navegador persistente, refresque credenciales y valide su estado de salud.

## What Changes

- Entidad `social_account` persistida por workspace soportando múltiples cuentas por plataforma (`youtube`, `tiktok`, `instagram`), alias editable, cuenta por defecto por plataforma, estado de conexión y método de autenticación (`api` u `playwright`).
- Flujos OAuth 2.0 locales para YouTube (app instalada con `GOOGLE_CLIENT_SECRET_FILE` y scopes `youtube.upload`, `youtube.readonly`, `youtube.force-ssl`), TikTok (`TIKTOK_CLIENT_KEY`/`TIKTOK_CLIENT_SECRET`, detectando si `video.publish` está aprobado o si opera en modo inbox con `video.upload`) e Instagram Graph (`META_APP_ID`/`META_APP_SECRET`, cuentas Business/Creator vinculadas a página de Facebook con `instagram_content_publish`).
- Flujo "Conectar con navegador" que abre Chromium visible con perfil persistente aislado en `storage/accounts/<account_id>/profile` para que el usuario inicie sesión manualmente (incluyendo 2FA) y detecta cuando la sesión queda activa.
- Almacenamiento cifrado en disco de credenciales OAuth (`storage/accounts/<account_id>/credentials.enc`) protegido con Fernet y clave maestra en Keychain de macOS (vía `keyring`) o `WINCLIP_SECRET_KEY`, refresco automático de tokens y garantía estricta de no exponer secretos en repositorio, logs, API ni `winclip doctor`.
- Comprobación de salud por cuenta (resolviendo nombre, `@handle`, avatar, capacidades y estado) e importación opcional de tokens locales existentes del usuario (`tokens/*.json`) en modo solo lectura sin copiar los archivos fuente al repositorio.
- Interfaz web en `/accounts` con tarjetas agrupadas por plataforma, acciones para añadir, importar, renombrar alias, marcar como cuenta por defecto, probar conexión, reconectar y eliminar.

**Fuera de alcance:** publicación o programación de videos (`add-publishers`), analíticas o métricas de cuentas, resolución automática de CAPTCHAs o 2FA, almacenamiento de credenciales en la nube y gestión multi-usuario.

## Capabilities

### New Capabilities
- `social-accounts`: conexión, almacenamiento cifrado, refresco de tokens, importación local, comprobación de salud y gestión multi-cuenta por plataforma (YouTube, TikTok e Instagram) vía API oficial o sesión persistente de navegador.

### Modified Capabilities

## Impact

- Backend (`apps/api`): nuevos módulos `winclip/accounts/{crypto,oauth,browser_login,importer,health}.py` y `winclip/publishers/playwright/session.py`, router `winclip/routers/accounts.py`, tabla `social_account` en `core/models.py`, ampliación de `core/config.py` (`WINCLIP_SECRET_KEY`) y `core/doctor.py`, comandos CLI `winclip accounts`.
- Frontend (`apps/web`): página y componentes de `/accounts` para conectar, importar y administrar cuentas por plataforma.
- Cliente tipado (`packages/api-client`): regeneración desde OpenAPI con los endpoints de cuentas.
- Dependencias Python nuevas: `cryptography`, `keyring`, `google-auth`, `google-auth-oauthlib`, `google-api-python-client`, `playwright`.
