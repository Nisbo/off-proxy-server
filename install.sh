#!/usr/bin/env bash
set -Eeuo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run as root / Als root ausführen.' >&2; exit 1; }
temporary=$(mktemp -d)
trap 'rm -rf -- "$temporary"' EXIT
# Resolve main once; bootstrap and application must come from the same commit.
curl -fsSL --proto '=https' --proto-redir '=https' --retry 2 --connect-timeout 15 --max-time 90 \
  https://api.github.com/repos/Nisbo/off-proxy-server/commits/main -o "$temporary/commit.json"
release=$(sed -nE '/^[[:space:]]*"sha":/ {s/^[[:space:]]*"sha":[[:space:]]*"([a-f0-9]{40})".*/\1/;p;q;}' "$temporary/commit.json")
[[ $release =~ ^[a-f0-9]{40}$ ]] || { echo 'Invalid GitHub commit.' >&2; exit 1; }
curl -fsSL --proto '=https' --proto-redir '=https' --retry 2 --connect-timeout 15 --max-time 90 \
  "https://raw.githubusercontent.com/Nisbo/off-proxy-server/$release/off-proxy" -o "$temporary/off-proxy"
OFF_PROXY_BOOTSTRAP_COMMIT=$release bash "$temporary/off-proxy" install "$@"
