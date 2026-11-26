#!/usr/bin/env bash
# Hook de gitleaks para pre-commit.
#
# - Con nombres de archivo (pre-commit run --files …): escanea el contenido de cada archivo.
# - Sin nombres de archivo (hook normal en `git commit`): escanea lo que está en el índice.
#
# Requiere el binario `gitleaks` (brew install gitleaks). Nunca imprime el valor del secreto:
# se usa --redact en todas las invocaciones.
set -euo pipefail

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "gitleaks no está instalado. Instálalo con: brew install gitleaks" >&2
  exit 1
fi

if [ "$#" -gt 0 ]; then
  status=0
  for file in "$@"; do
    [ -f "$file" ] || continue
    case "$file" in
      *.png | *.jpg | *.jpeg | *.gif | *.webp | *.ico | *.pdf | *.woff | *.woff2 | *.ttf | *.otf | *.zip | *.gz)
        continue
        ;;
    esac
    if ! gitleaks stdin --no-banner --redact --log-level error <"$file"; then
      echo "gitleaks: posible secreto en $file" >&2
      status=1
    fi
  done
  exit "$status"
fi

exec gitleaks git --pre-commit --staged --redact --no-banner
