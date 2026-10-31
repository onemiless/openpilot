#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != --check-runtime ) ]]; then
  echo 'Only --check-runtime is supported' >&2
  exit 2
fi
bash ./prepare_payload.sh
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
unset PYTHONHOME
export PYTHONPATH="$PWD"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/data/sp-flasher-cache}"
# Verify native executables before using a bundled interpreter to inspect itself.
if command -v sha256sum >/dev/null; then
  (cd runtime && sha256sum --quiet -c SHA256SUMS)
else
  (cd runtime && shasum -a 256 -c SHA256SUMS >/dev/null)
fi
python="$(command -v python3 || true)"
if [[ -z "$python" ]] || ! "$python" runtime_probe.py --python; then
  export PYTHONPATH="$PWD/runtime/numpy:$PWD"
  if [[ -z "$python" ]] || ! "$python" runtime_probe.py --python; then
    python="$PWD/runtime/python/bin/python3"
    "$python" runtime_probe.py --python
  fi
fi
if ! command -v fuser >/dev/null || ! fuser -V >/dev/null 2>&1; then
  export PATH="$PWD/runtime/tools:$PATH"
  export LD_LIBRARY_PATH="$PWD/runtime/llvm:$PWD/runtime/libusb${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  fuser -V >/dev/null
fi
if ! "$python" runtime_probe.py --libusb; then
  export LIBUSB_PATH="$PWD/runtime/libusb/libusb-1.0.so.0"
  export LD_LIBRARY_PATH="$PWD/runtime/libusb${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  "$python" runtime_probe.py --libusb
fi
if ! "$python" runtime_probe.py --llvm; then
  export LLVM_PATH="$PWD/runtime/llvm/libLLVM.so"
  export LD_LIBRARY_PATH="$PWD/runtime/llvm${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  "$python" runtime_probe.py --llvm
fi
# Native dependency paths can affect an existing NumPy extension's C++ dependencies.
if ! "$python" runtime_probe.py --python; then
  export PYTHONPATH="$PWD/runtime/numpy:$PWD"
  if ! "$python" runtime_probe.py --python; then
    python="$PWD/runtime/python/bin/python3"
    "$python" runtime_probe.py --python
  fi
fi
if [[ "${1:-}" == --check-runtime ]]; then
  exec "$python" runtime_probe.py --report
fi
exec "$python" runtime_probe.py --run
