#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
export XDG_CACHE_HOME=/data/sp-flasher-cache
if [[ "$EUID" == 0 ]]; then
  exec bash ./runtime.sh "$@"
fi
exec sudo --preserve-env=XDG_CACHE_HOME bash ./runtime.sh "$@"
