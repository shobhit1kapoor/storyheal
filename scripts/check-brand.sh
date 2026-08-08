#!/usr/bin/env bash
set -euo pipefail

set +e
matches="$(rg -n -i '\btgo(\.ai)?\b' . \
  --glob '!THIRD_PARTY_NOTICES/**' \
  --glob '!.storyheal-import/**' \
  --glob '!**/*lock*' \
  --glob '!scripts/check-brand.sh')"
status=$?
set -e

if [[ $status -eq 0 ]]; then
  printf '%s\n' "$matches"
  echo "Legacy brand reference found outside THIRD_PARTY_NOTICES." >&2
  exit 1
fi
if [[ $status -ne 1 ]]; then
  echo "Brand scanner failed with status $status." >&2
  exit "$status"
fi
echo "Brand boundary verified."
