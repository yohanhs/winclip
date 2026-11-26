# repo-security Specification

## Purpose
Garantiza que el repositorio público de WinClip nunca contenga secretos, credenciales, tokens, perfiles de navegador ni contenido multimedia del usuario.

## Requirements

### Requirement: Exclusión de datos sensibles
El repositorio SHALL ignorar por defecto `.env*` (salvo `.env.example`), `client_secret*.json`, cualquier carpeta `tokens/`, `storage/`, perfiles de Playwright, cookies y archivos multimedia (`*.mp4`, `*.mov`, `*.wav`, `*.mp3`, `*.mkv`, `*.webm`).

#### Scenario: Archivo de secretos creado por error
- **WHEN** existe `apps/api/.env` o `client_secret_123.json` en el árbol de trabajo
- **THEN** `git status` no los lista como archivos a añadir

### Requirement: Escaneo de secretos antes del commit
El repositorio SHALL bloquear commits que contengan patrones de secretos mediante un hook de pre-commit con gitleaks.

#### Scenario: Commit con una clave
- **WHEN** un desarrollador intenta commitear un archivo con una clave de API de Google o NVIDIA
- **THEN** el commit es rechazado e indica el archivo y la línea

### Requirement: Escaneo de secretos en CI
La integración continua SHALL ejecutar gitleaks, el lint y los tests de ambas apps en cada push y pull request, y fallar si alguno falla.

#### Scenario: Push con secreto
- **WHEN** se hace push de un commit con un secreto que se saltó el hook local
- **THEN** el workflow de CI falla en el paso de gitleaks

### Requirement: Licencias del contenido distribuido
El repositorio SHALL distribuirse bajo AGPL-3.0 e incluir únicamente fuentes con licencia libre (OFL o equivalente), acompañadas de su archivo de licencia.

#### Scenario: Revisión de fuentes incluidas
- **WHEN** se lista `assets/fonts`
- **THEN** cada familia tiene su archivo de licencia y no hay fuentes comerciales
