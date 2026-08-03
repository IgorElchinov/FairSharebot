#!/usr/bin/env bash
# Builds the contracts and copies just the ABI (not full artifacts) into
# fairsharebot/chain/abi/, which is what the Python bot actually ships.
set -euo pipefail

cd "$(dirname "$0")"
forge build

DEST="../fairsharebot/chain/abi"
mkdir -p "$DEST"

for name in FairShareToken Settlement; do
  jq '.abi' "out/${name}.sol/${name}.json" > "$DEST/${name}.json"
  echo "wrote $DEST/${name}.json"
done
