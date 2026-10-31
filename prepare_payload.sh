#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
check() {
  if command -v sha256sum >/dev/null; then sha256sum --quiet -c -; else shasum -a 256 -c - >/dev/null; fi
}
while IFS=$'\t' read -r digest target prefix; do
  if [[ -f "$target" ]] && printf '%s  %s\n' "$digest" "$target" | check; then continue; fi
  (cd payload && check < SHA256SUMS)
  mkdir -p "$(dirname "$target")"
  temporary="$target.tmp"
  trap 'rm -f "$temporary"' EXIT
  cat payload/"$prefix".part* > "$temporary"
  printf '%s  %s\n' "$digest" "$temporary" | check
  mv "$temporary" "$target"
  trap - EXIT
done < payload/targets.tsv
