import time
from urllib.error import HTTPError
from unittest.mock import patch

import pytest

import app
import components
import releases
from .test_app import db
from .test_security import secured

SHA = "a" * 40


def published(tag, *, beta=False, draft=False):
    return {"tag_name": tag, "draft": draft, "prerelease": beta,
            "body": "Release notes", "published_at": "2026-11-22T10:00:00Z"}


def test_latest_stable_uses_the_same_published_release_as_the_installer():
    tag = "v0.2.0"
    with patch.object(releases, "json_url", side_effect=[published(tag), {"sha": SHA}]) as get:
        release = releases.latest("stable")
    assert release["version"] == tag[1:]
    assert release["commit"] == SHA
    assert [call.args[0] for call in get.call_args_list] == [
        releases.API+"/releases/latest", releases.API+"/commits/tags/"+tag,
    ]


def test_missing_stable_release_returns_no_candidate():
    error = HTTPError(releases.API+"/releases/latest", 404, "No release", {}, None)
    with patch.object(releases, "json_url", side_effect=error) as get:
        assert releases.latest("stable") is None
    assert get.call_count == 1


def test_beta_selects_the_highest_published_beta_and_resolves_its_tag():
    entries = [published("v0.9.0", draft=True), published("v0.2.0"),
               published("v0.3.0-beta.9", beta=True), published("v0.3.0-beta.10", beta=True),
               published("v0.4.0-beta.1"), published("v0.9.0", beta=True)]
    with patch.object(releases, "json_url", side_effect=[entries, {"sha": SHA}]) as get:
        release = releases.latest("beta")
    assert release["commit"] == SHA
    assert release["version"] == "0.3.0-beta.10"
    assert get.call_args_list[1].args[0].endswith("/commits/tags/v0.3.0-beta.10")


def test_no_beta_release_has_no_branch_fallback():
    with patch.object(releases, "json_url", return_value=[published("v0.2.0")]) as get:
        assert releases.latest("beta") is None
    assert get.call_count == 1
    assert releases.version_key("0.2.0-beta.1") < releases.version_key("0.2.0")
    assert not releases.available({"commit": SHA, "version": "0.2.0-beta.1"}, "0.2.0", "b"*40)
    assert releases.available({"commit": SHA, "version": "0.2.0"}, "0.2.0", "b"*40)
    assert not releases.available({"commit": SHA, "version": "0.2.0"}, "0.2.0", SHA)


def test_program_release_check_is_manual_and_install_requires_exact_checked_commit(secured):
    server, client = secured
    path = "/ui/program/"
    data = {"channel": "beta", "version": "99.1.0-beta.1", "commit": SHA,
            "notes": "Notes", "url": "https://github.com/Nisbo/off-proxy-server/releases/tag/v99.1.0-beta.1"}
    components.heartbeat(server.db)
    with patch.object(releases, "latest", return_value=data) as lookup:
        assert client.call(path+"check", {"channel":"beta"})[0] == 401
        assert client.login()[0] == 200
        assert client.call("/ui/status")[0] == 200
        assert client.call("/ui/components")[0] == 200
        lookup.assert_not_called()
        assert client.call(path+"check", {"channel":"head"})[0] == 400
        assert client.call(path+"check", {"channel":"beta"}, headers={"X-Off-Proxy-Control":"bad"})[0] == 403
        assert client.call(path+"check", {"channel":"beta"})[1] == {"release":data,"available":True,"installed":app.VERSION}
        assert server.db.components.find_one({"_id":"host"})["status"] == "idle"
        lookup.assert_called_once_with("beta")
    approved = {"channel":"beta", "commit":SHA, "confirmed":True}
    assert client.call(path+"update", dict(approved, confirmed=1))[0] == 400
    assert client.call(path+"update", dict(approved, commit="b"*40))[0] == 409
    assert client.call(path+"update", dict(approved, channel="stable"))[0] == 409
    assert client.call(path+"update", approved, headers={"X-Off-Proxy-Control":"bad"})[0] == 403
    server.db.scheduler.insert_one({"_id":"sync","phase":"running"})
    assert client.call(path+"update", approved)[0] == 409
    server.db.scheduler.delete_one({"_id":"sync"})
    assert client.call(path+"update", approved)[1]["queued"] is True
    assert client.call("/ui/components/check", {})[1]["queued"] is False
    assert client.call(path+"update", approved)[1]["queued"] is False
    assert components.claim(server.db) == f"program-update beta {SHA} 99.1.0-beta.1"
    assert components.claim(server.db) == ""
    server.db.program_releases.update_one({"_id":"beta"}, {"$set":{"checked_at":time.time()-3601}})
    assert client.call(path+"update", approved)[0] == 409


def test_unavailable_release_service_returns_safe_error(secured):
    _, client = secured
    assert client.login()[0] == 200
    with patch.object(releases, "latest", side_effect=OSError("private details")):
        assert client.call("/ui/program/check", {"channel":"stable"})[:2] == (502, {"error":"program_check_failed"})
