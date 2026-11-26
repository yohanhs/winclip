# Design

## Context

Ver `proposal.md` para la motivación. Este change depende de `add-api-jobs` (base de datos SQLite/SQLModel, estructura de routers FastAPI, workspace por defecto) y para su interfaz web de `add-web-ui-cards` (layout, navegación, cliente generado `packages/api-client`).

`docs/architecture.md` fija:
- Variables de entorno (§4): `GOOGLE_CLIENT_SECRET_FILE`, `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `META_APP_ID`, `META_APP_SECRET`.
- Layout de almacenamiento (§5): `storage/accounts/<account_id>/` (gitignored).
- Modelo base `social_account` (§7): `id, workspace_id, platform, display_name, handle, auth_method, credentials_ref, status, last_check_at`.
- Ubicación de sesión Playwright (§3): `winclip/publishers/playwright/session.py` y router `winclip/routers/accounts.py`.

## Goals / Non-Goals

**Goals:**
- Soportar N cuentas independientes por plataforma (caso real del usuario: HookVault en YouTube + TikTok y nuevas cuentas adicionales) con selección ergonómica de cuenta por defecto y alias.
- Almacenar credenciales OAuth cifradas en reposo sin introducir infraestructura externa (sin Vault ni Redis) y sin escribir secretos en SQLite ni en el repo.
- Ofrecer una vía oficial (OAuth) y una vía práctica de respaldo (navegador visible persistente con Playwright) manteniendo una interfaz uniforme para `add-publishers`.
- Reutilizar tokens existentes del usuario (`/Volumes/yohan/Youtube API/tokens/*.json`) sin duplicar archivos sensibles en el repo.

**Non-Goals:**
- Subida o publicación de videos (pertenece a `add-publishers`).
- Evasión automatizada de CAPTCHAs, antibot o 2FA (el usuario interactúa directamente en Chromium visible).
- Rotación automática de claves multi-tenant en KMS externo (la interfaz `CredentialStore` deja esa puerta abierta para un futuro SaaS).

## Decisions

1. **Cifrado de credenciales: Fernet (`cryptography`) + clave maestra en Keychain de macOS (`keyring`) con fallback a `WINCLIP_SECRET_KEY`.**
   - Resolución de clave maestra (`winclip/accounts/crypto.py`):
     1. Si `Settings.winclip_secret_key` está definida en `.env`/entorno, se usa (ideal para CI, scripts headless o despliegue SaaS futuro).
     2. Si no está definida, se busca en macOS Keychain vía `keyring.get_password("winclip", "master_key")`. Si no existe, se genera con `Fernet.generate_key()` y se guarda automáticamente en Keychain.
   - Cada cuenta API guarda su payload JSON serializado en `storage/accounts/<account_id>/credentials.enc` (permisos `0600`) cifrado con Fernet (AES-128-CBC + HMAC-SHA256 con autenticación de integridad). En SQLite solo se guarda `credentials_ref = "accounts/<account_id>/credentials.enc"` (ruta relativa), nunca tokens.
   - *Alternativas consideradas:*
     - Solo `keyring` por cada cuenta: en macOS Keychain los blobs JSON grandes de OAuth y el listado/borrado de entradas por workspace son más frágiles, y dificulta portar el storage o ejecutar tests en entornos sin Keychain.
     - Solo `WINCLIP_SECRET_KEY` en `.env`: obliga al usuario a generar y pegar manualmente una clave antes de conectar su primera cuenta.
   - La combinación Fernet + Keychain (con override vía `WINCLIP_SECRET_KEY`) ofrece cero fricción en Mac M1, cifrado fuerte en disco y compatibilidad con entornos sin Keychain.

2. **Flujos OAuth 2.0 por plataforma (`winclip/accounts/oauth.py`).**
   - Estado OAuth efímero (`state`, `code_verifier` para PKCE, `workspace_id`, `platform`, `expires_at` con TTL 10 min) almacenado en memoria del proceso API (suficiente para single-user local) y validado en el callback para prevenir CSRF.
   - **YouTube:** `google-auth-oauthlib` (`Flow.from_client_secrets_file(GOOGLE_CLIENT_SECRET_FILE, scopes=[youtube.upload, youtube.readonly, youtube.force-ssl])`) con callback en `http://localhost:8000/api/accounts/oauth/youtube/callback` (o redirección a la web `http://localhost:3000/accounts?connected=<id>`), `access_type="offline"` y `prompt="consent"` para asegurar `refresh_token`. Consulta `youtube.channels().list(part="snippet", mine=True)` para extraer `channel_id`, `display_name`, `handle` (`customUrl`) y `avatar_url`.
   - **TikTok:** OAuth v2 (`https://www.tiktok.com/v2/auth/authorize/`) con PKCE y scopes configurables: solicita `user.info.basic,video.upload` y opcionalmente `video.publish` si el usuario marca que su app tiene Direct Post aprobado (o intenta `video.publish` y registra los `scope` realmente devueltos por el token endpoint en `capabilities_json`: `{"direct_post": "video.publish" in granted, "inbox_only": "video.publish" not in granted}`). Consulta `/v2/user/info/` para nombre y avatar.
   - **Instagram Graph:** OAuth Meta (`https://www.facebook.com/v21.0/dialog/oauth`) con scopes `instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement`. Intercambia el token de corta duración por un long-lived user token (~60 días), consulta `/me/accounts?fields=id,name,access_token,instagram_business_account{id,username,name,profile_picture_url}` y si encuentra >1 cuenta IG devuelve una selección temporal (`pending_selection_token`, TTL 5 min) para que la UI muestre las cuentas disponibles y el usuario elija cuáles guardar.
   - *Alternativa descartada:* servidor OAuth local aparte en otro puerto. Reutilizar FastAPI en `API_PORT` (8000) simplifica las Redirect URIs en Google/TikTok/Meta y evita puertos aleatorios.

3. **Sesión persistente Playwright y login interactivo (`winclip/publishers/playwright/session.py`, `winclip/accounts/browser_login.py`).**
   - Cada cuenta `playwright` usa su propio directorio `storage/accounts/<account_id>/profile` (permisos `0700`) abierto con `playwright.sync_api` / `async_api` `chromium.launch_persistent_context(user_data_dir=..., headless=False)`.
   - Un registro de sesiones de login activas evita abrir dos ventanas simultáneas para la misma cuenta (`asyncio.Lock` por `account_id`).
   - Detección de login: polling periódico (cada 2 s, timeout configurable default 300 s) verificando cookies de sesión conocidas (p. ej. `sessionid` en TikTok o `sessionid`/`ds_user_id` en Instagram) o navegación a URL autenticada, complementado con un endpoint `POST /api/accounts/{id}/browser-login/confirm` para confirmación manual si la red cambia nombres de cookie.
   - Al completar, intenta leer handle/display_name de la página de perfil (si no puede, permite editar el alias), cierra el contexto para volcar cookies al disco y marca `status = "connected"`.
   - *Alternativa descartada:* exportar/importar cookies JSON sueltas. Un perfil persistente de Chromium mantiene localStorage, IndexedDB y huella consistente, reduciendo re-logins y retos 2FA.

4. **Refresco de tokens y health check (`winclip/accounts/health.py`).**
   - Un método común `get_valid_credentials(account)` refresca automáticamente cuando `expires_at` está a menos de 5 min (YouTube vía `google.oauth2.credentials.Credentials.refresh`, TikTok vía `POST /v2/oauth/token/` con `grant_type=refresh_token`, Instagram renovando long-lived token cuando falten <10 días vía `fb_exchange_token` / `ig_refresh_token`) y re-cifra atómicamente `credentials.enc` (write temp + `os.replace`).
   - `check_account(account)` actualiza `display_name`, `handle`, `avatar_url`, `status`, `token_expires_at`, `last_check_at` y `last_error`. Para cuentas `playwright`, abre brevemente el contexto persistente en modo headless (o configurable) para verificar cookies/acceso a la página de subida/perfil sin interactuar ni enviar formularios.

5. **Importación de tokens existentes del usuario (`winclip/accounts/importer.py`).**
   - Soporta un archivo `.json` individual o un directorio de archivos `*.json` (como `/Volumes/yohan/Youtube API/tokens/`).
   - Detecta formato Google Authorized User (`refresh_token` + `client_id` + `client_secret`) y formato TikTok token JSON (`access_token`/`refresh_token`/`open_id`).
   - Lee el archivo en modo solo lectura (`r`), crea la cuenta, cifra el payload en `storage/accounts/<account_id>/credentials.enc`, ejecuta un health check para rellenar nombre/handle/avatar y jamás copia el archivo origen al repositorio ni lo modifica.

6. **Integración con `winclip doctor` y `Settings`.**
   - Se añade `WINCLIP_SECRET_KEY: str = ""` en `core/config.py` y `.env.example`.
   - `core/doctor.py` incorpora checks informativos (`ok`/`warn`, nunca bloqueantes si el usuario solo usa YouTube o Playwright): estado de `GOOGLE_CLIENT_SECRET_FILE` (ausente / archivo encontrado / ruta inexistente), `TIKTOK_CLIENT_KEY`/`SECRET` (presente/ausente), `META_APP_ID`/`SECRET` (presente/ausente), y backend de cifrado activo (`env` o `keychain`, sin mostrar la clave).

7. **Justificación de nuevas dependencias Python (`apps/api/pyproject.toml`).**
   - `cryptography`: estándar de facto en Python para cifrado autenticado (Fernet); sin alternativa segura en stdlib.
   - `keyring`: acceso nativo al Keychain de macOS para proteger la clave maestra sin obligar a pegarla en `.env`.
   - `google-auth`, `google-auth-oauthlib`, `google-api-python-client`: SDK oficial de Google para OAuth instalado y YouTube Data API v3 (compatible con los tokens existentes de `subir.py` y reutilizado por `add-publishers`).
   - `playwright`: automatización de Chromium para sesiones persistentes de login manual (y fallback de publicación en `add-publishers`); el binario Chromium ya está instalado en la máquina.
   - Para TikTok OAuth e Instagram Graph se usa `httpx` (ya presente en `apps/api`), evitando SDKs de terceros poco mantenidos.

## Contratos

Extensiones compatibles sobre `docs/architecture.md §4`, `§5` y `§7`:

- **Variable de entorno nueva (opcional):** `WINCLIP_SECRET_KEY` (vacía por defecto; si se omite se usa Keychain de macOS vía `keyring`).
- **Tabla `social_account` (extensión compatible con §7):**
  `id (ULID), workspace_id, platform (youtube|tiktok|instagram), display_name, handle, alias (nullable), avatar_url (nullable), auth_method (api|playwright), credentials_ref, status (pending|connected|expired|error), is_default (bool), capabilities_json (TEXT/JSON), external_account_id (nullable), token_expires_at (nullable), last_check_at (nullable), last_error (nullable), created_at, updated_at`.
  Invariante: como máximo un registro con `is_default = true` por `(workspace_id, platform)`.
- **Layout en `STORAGE_DIR`:**
  - `storage/accounts/<account_id>/credentials.enc` (permisos `0600`, Fernet sobre JSON de credenciales API).
  - `storage/accounts/<account_id>/profile/` (permisos `0700`, directorio `user_data_dir` de Chromium para `auth_method="playwright"`).
- **Endpoints `/api/accounts`:**
  - `GET /api/accounts` → lista cuentas del workspace agrupables por plataforma (nunca incluye secretos ni `credentials_ref` absoluto).
  - `PATCH /api/accounts/{id}` → actualiza `alias` y/o `is_default` (desmarca atómicamente la anterior por defecto de esa plataforma).
  - `DELETE /api/accounts/{id}` → elimina la cuenta y borra `storage/accounts/<id>/`.
  - `POST /api/accounts/{id}/check` → ejecuta health check + refresco si procede y devuelve estado actualizado.
  - `POST /api/accounts/oauth/{platform}/start` → devuelve `{auth_url, state}` para redirigir al usuario (acepta `account_id` opcional para reconexión).
  - `GET /api/accounts/oauth/{platform}/callback` → completa el intercambio OAuth y redirige a `/accounts` (o devuelve selección de cuentas IG pendientes).
  - `POST /api/accounts/oauth/instagram/select` → confirma las cuentas Business/Creator elegidas de una sesión Meta recién autorizada.
  - `POST /api/accounts/browser-login/start` → crea (o reutiliza para reconexión) cuenta `playwright` y lanza Chromium visible; devuelve `{account_id, session_status}`.
  - `GET /api/accounts/{id}/browser-login/status` → estado del login interactivo (`waiting`, `connected`, `timeout`, `cancelled`, `error`).
  - `POST /api/accounts/{id}/browser-login/confirm` / `cancel` → confirmación manual o cancelación de la ventana de login.
  - `POST /api/accounts/import` → recibe `{path, platform?, alias?}` e importa uno o varios tokens existentes en modo solo lectura.
- **CLI:** `winclip accounts list`, `winclip accounts check [id]`, `winclip accounts import <path>`.

## Risks / Trade-offs

- [El usuario pierde la clave de Keychain o cambia `WINCLIP_SECRET_KEY`] → `credentials.enc` no puede descifrarse; se captura `InvalidToken`, se marca la cuenta como `error` con mensaje claro ("Clave de cifrado cambiada; reconecta la cuenta") sin tumbar la API.
- [Tokens de Instagram expiran a los 60 días si el usuario no abre WinClip] → El health check y el pre-check de publicación refrescan proactivamente cuando faltan <10 días; si ya expiró, la UI muestra badge `Expirada` y botón "Reconectar" en un clic.
- [Google OAuth en modo "Testing" caduca refresh tokens cada 7 días] → Documentar claramente en la guía de configuración / README el comportamiento de apps en modo Testing en Google Cloud Console y mostrar error accionable de reconexión.
- [TikTok o Instagram cambian las cookies o rutas de login en modo Playwright] → Combinar detección automática por cookies/URL con botón manual "Confirmar sesión" en la UI para que el flujo nunca quede bloqueado.
- [Exposición accidental de tokens en excepciones o logs HTTP] → Filtro/sanitización en el logger de `accounts` y tests dedicados verificando que ningún valor de token o secret aparece en logs, respuestas API ni salida de `winclip doctor`.
