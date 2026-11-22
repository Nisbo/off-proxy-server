#!/usr/bin/env bash
set -Eeuo pipefail

[[ $(id -u) == 0 ]] || { echo 'Run as root / Als root ausführen.' >&2; exit 1; }
ref=main
expected=
development=false
if [[ ${1:-} == --main ]]; then development=true; shift; fi
if [[ $# -gt 1 || ${1:-} == -* ]]; then
  echo 'Usage: bash install.sh [--main] [/installation/path]' >&2
  exit 1
fi

temporary=$(mktemp -d)
trap 'rm -rf -- "$temporary"' EXIT
api=https://api.github.com/repos/Nisbo/off-proxy-server
download() {
  curl -fsSL --proto '=https' --proto-redir '=https' --retry 2 --connect-timeout 15 --max-time 90 "$1" -o "$2"
}
if ! "$development"; then
  if ! download "$api/releases/latest" "$temporary/latest.json"; then
    echo 'No stable release could be downloaded / Kein stabiles Release konnte geladen werden.' >&2
    exit 1
  fi
  tag=$(sed -nE '/^[[:space:]]*"tag_name":/ {s/^[[:space:]]*"tag_name":[[:space:]]*"(v[0-9]+\.[0-9]+\.[0-9]+)".*/\1/;p;q;}' "$temporary/latest.json")
  [[ $tag =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'Invalid stable release tag.' >&2; exit 1; }
  ref=tags/$tag
  expected=${tag#v}
fi

# Pin both the installer and the application archive to a single commit.
download "$api/commits/$ref" "$temporary/commit.json"
release=$(sed -nE '/^[[:space:]]*"sha":/ {s/^[[:space:]]*"sha":[[:space:]]*"([a-f0-9]{40})".*/\1/;p;q;}' "$temporary/commit.json")
[[ $release =~ ^[a-f0-9]{40}$ ]] || { echo 'Invalid GitHub commit.' >&2; exit 1; }
download "https://raw.githubusercontent.com/Nisbo/off-proxy-server/$release/off-proxy" "$temporary/off-proxy"
OFF_PROXY_BOOTSTRAP_COMMIT=$release OFF_PROXY_BOOTSTRAP_VERSION=$expected bash "$temporary/off-proxy" install "$@"
