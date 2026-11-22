"""Resolve published OFF Proxy releases to immutable Git commits."""
import re
import sys

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


def tag_commit(tag):
    obj = json_url(f"{API}/git/ref/tags/{tag}")["object"]
    for _ in range(4):
        if not COMMIT.fullmatch(obj["sha"]):
            raise ValueError("Invalid tag object")
        if obj["type"] == "commit":
            return obj["sha"]
        if obj["type"] != "tag":
            break
        obj = json_url(f"{API}/git/tags/{obj['sha']}")["object"]
    raise ValueError("Tag does not point to a commit")


def latest(channel):
    if channel not in CHANNELS:
        raise ValueError("Invalid release channel")
    # GitHub returns the most recent releases first. Find the highest version
    # within the first page containing a release for the selected channel.
    for page in range(1, 11):
        entries = json_url(f"{API}/releases?per_page=100&page={page}")
        if not isinstance(entries, list):
            raise ValueError("Invalid release list")
        candidates = []
        for row in entries:
            tag = row.get("tag_name", "")
            if not tag.startswith("v") or not VERSION.fullmatch(tag[1:]):
                continue
            key = version_key(tag[1:])
            stable = channel == "stable"
            if (row.get("draft") is not False or not row.get("published_at")
                    or row.get("prerelease") is not (channel == "beta") or key[3] != stable):
                continue
            candidates.append((key, row))
        if candidates:
            _, row = max(candidates, key=lambda candidate: candidate[0])
            tag = row["tag_name"]
            return {"channel": channel, "version": tag[1:], "commit": tag_commit(tag),
                    "notes": (row.get("body") or "")[:12000], "published_at": row["published_at"],
                    "url": f"https://github.com/Nisbo/off-proxy-server/releases/tag/{tag}"}
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
