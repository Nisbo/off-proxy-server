#!/usr/bin/env bash
set -Eeuo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run as root / Als root ausführen.' >&2; exit 1; }
temporary=$(mktemp)
trap 'rm -f -- "$temporary"' EXIT
curl -fsSL --retry 2 --connect-timeout 15 --max-time 90 \
  https://raw.githubusercontent.com/Nisbo/off-proxy-server/main/off-proxy -o "$temporary"
bash "$temporary" install "$@"
