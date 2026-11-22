"""Resolve published OFF Proxy releases to immutable Git commits."""
import re
import sys
from urllib.error import HTTPError

from components import json_url

API = "https://api.github.com/repos/Nisbo/off-proxy-server"
VERSION = re.compile(r"(\d{1,6})\.(\d{1,6})\.(\d{1,6})(?:-beta\.(\d{1,6}))?", re.ASCII)
COMMIT = re.compile(r"[0-9a-f]{40}")
CHANNELS = ("stable", "beta")


def version_key(version):
    match = VERSION.fullmatch(version)
    if not match:
        raise ValueError("Invalid release version")
    major, minor, patch, beta = match.groups()
    return int(major), int(minor), int(patch), beta is None, int(beta or 0)


def release_record(channel, row):
    tag = row["tag_name"]
    commit = json_url(f"{API}/commits/tags/{tag}")["sha"]
    if not COMMIT.fullmatch(commit):
        raise ValueError("Invalid release commit")
    return {"channel": channel, "version": tag[1:], "commit": commit,
            "notes": (row.get("body") or "")[:12000], "published_at": row["published_at"],
            "url": f"https://github.com/Nisbo/off-proxy-server/releases/tag/{tag}"}


def release_key(row, *, beta):
    tag = row.get("tag_name", "")
    if not tag.startswith("v") or not VERSION.fullmatch(tag[1:]):
        return None
    key = version_key(tag[1:])
    if (row.get("draft") is not False or not row.get("published_at")
            or row.get("prerelease") is not beta or key[3] == beta):
        return None
    return key


def latest(channel):
    if channel not in CHANNELS:
        raise ValueError("Invalid release channel")
    if channel == "stable":
        try:
            row = json_url(f"{API}/releases/latest")
        except HTTPError as error:
            if error.code == 404:
                return None
            raise
        if release_key(row, beta=False) is None:
            raise ValueError("Invalid stable release")
        return release_record(channel, row)

    # Find the highest beta version within the first page of recent beta releases.
    for page in range(1, 11):
        entries = json_url(f"{API}/releases?per_page=100&page={page}")
        if not isinstance(entries, list):
            raise ValueError("Invalid release list")
        candidates = [(key, row) for row in entries if (key := release_key(row, beta=True))]
        if candidates:
            _, row = max(candidates, key=lambda candidate: candidate[0])
            return release_record(channel, row)
        if len(entries) < 100:
            return None
    raise ValueError("Release lookup exceeded its page limit")


def available(target, version, commit):
    if target is None:
        return False
    candidate, installed = version_key(target["version"]), version_key(version)
    return candidate > installed or (candidate == installed and bool(COMMIT.fullmatch(commit or ""))
                                     and target["commit"] != commit)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in CHANNELS:
        raise SystemExit("Expected stable or beta")
    try:
        release = latest(sys.argv[1])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise SystemExit("Published releases could not be checked / Veröffentlichte Releases konnten nicht geprüft werden.")
    if release is None:
        raise SystemExit("No published release in this channel / Kein veröffentlichtes Release in diesem Kanal.")
    print(release["commit"], release["version"])
