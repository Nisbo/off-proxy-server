"""Exercise the actual shell installer/updater with a fake Docker/GitHub boundary."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

import pytest

SOURCE = Path(__file__).parent


@pytest.fixture
def installation(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    root = tmp_path / "installed"
    remote = tmp_path / "remote"
    remote.mkdir()
    log = tmp_path / "docker.log"
    env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"],
               OFF_PROXY_DIR=str(root), OFF_PROXY_BIN_DIR=str(tmp_path / "local-bin"),
               OFF_PROXY_LEGACY_DIR=str(tmp_path / "legacy"),
               FAKE_REMOTE=str(remote), FAKE_LOG=str(log), FAKE_RELEASE="a" * 40)
    programs = {
        "id": "#!/bin/sh\necho 0\n",
        "sleep": "#!/bin/sh\nexit 0\n",
        "curl": '''#!/usr/bin/env python3
import json,os,pathlib,shutil,sys
args=sys.argv[1:];dest=pathlib.Path(args[args.index('-o')+1]);url=next(a for a in args if a.startswith('https://'))
if 'api.github.com' in url:dest.write_text(json.dumps({'sha':os.environ['FAKE_RELEASE']},indent=2))
else:shutil.copyfile(pathlib.Path(os.environ['FAKE_REMOTE'])/(os.environ['FAKE_RELEASE']+'.tar.gz'),dest)
''',
        "docker": '''#!/usr/bin/env python3
import json,os,pathlib,sys
a=sys.argv[1:]
with open(os.environ['FAKE_LOG'],'a') as f:f.write(json.dumps(a)+'\\n')
if a[:2]==['compose','version'] or a[:1]==['ps']:sys.exit(0)
if '-f' not in a:sys.exit(9)
source=a[a.index('-f')+1]
if 'ps' in a:
    if os.environ.get('FAKE_RUNNING','1')=='1':print('existing-worker')
    sys.exit(0)
if 'exec' in a and any('busy=' in x for x in a):sys.exit(75 if os.environ.get('FAKE_BUSY')=='1' else 0)
if 'exec' in a and any('sys.argv[1]' in x for x in a):
    sys.exit(1 if os.environ.get('FAKE_BAD_RELEASE','@') in source else 0)
if 'build' in a and os.environ.get('FAKE_BUILD_FAIL')=='1':sys.exit(1)
if a[-2:]==['app.py','password']:
    data=sys.stdin.readline()
    pathlib.Path(os.environ['FAKE_LOG']+'.password-length').write_text(str(len(data.rstrip('\\n'))))
sys.exit(0)
''',
    }
    if not shutil.which("flock"):
        programs["flock"] = "#!/bin/sh\nexit 0\n"
    for name, content in programs.items():
        path = tools / name
        path.write_text(content)
        path.chmod(0o755)

    def archive(release):
        with tarfile.open(remote / (release + ".tar.gz"), "w:gz") as tar:
            for name in ("app.py", "dashboard.py", "control.py", "security.py", "web/index.html", "web/dashboard.css", "web/dashboard.js", "VERSION", "compose.yaml", "Dockerfile", ".dockerignore", "requirements.txt", "off-proxy"):
                data = (SOURCE / name).read_bytes()
                info = tarfile.TarInfo("off-proxy-server-" + release + "/" + name)
                info.size = len(data)
                info.mode = 0o755 if name == "off-proxy" else 0o644
                tar.addfile(info, io.BytesIO(data))
    archive("a" * 40)
    archive("b" * 40)

    def run(*args, **changes):
        return subprocess.run(["bash", str(SOURCE / "off-proxy"), *args],
                              env=dict(env, **changes), text=True, capture_output=True)
    return root, env, log, run


def docker_calls(log):
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_new_install_and_idempotent_update(installation):
    root, env, log, run = installation
    result = run("install")
    assert result.returncode == 0, result.stderr + result.stdout
    assert (root / ".state/current").read_text().strip() == "a" * 40
    secret = (root / ".env").read_bytes()
    assert len(secret.split(b"API_TOKEN=")[1].strip()) == 64
    assert (root / ".env").stat().st_mode & 0o777 == 0o600
    assert Path(env["OFF_PROXY_BIN_DIR"], "off-proxy").exists()
    log.write_text("")
    result = run("update")
    assert result.returncode == 0, result.stderr
    assert "Already current" in result.stdout
    assert not any("stop" in call or "up" in call for call in docker_calls(log))
    assert (root / ".env").read_bytes() == secret


def prepare_legacy(env):
    legacy = Path(env["OFF_PROXY_LEGACY_DIR"])
    legacy.mkdir()
    (legacy / "app.py").write_text('VERSION = "0.1.2"\n')
    (legacy / "compose.yaml").write_text('name: off-local-api\nx-app:\n  build: .\n')
    (legacy / "Dockerfile").write_text("FROM python:3.13-slim\n")
    (legacy / "requirements.txt").write_text("pymongo==4.15.5\n")
    (legacy / ".env").write_text("API_TOKEN=existing-secret-unchanged\nBIND_IP=127.0.0.1\nPORT=8097\n")
    (legacy / "data").mkdir()
    (legacy / "data/database").write_bytes(b"existing 36 GiB represented by sentinel")
    (legacy / "configdb").mkdir()
    return legacy


def test_migrate_existing_database_and_token_without_copying_data(installation):
    root, env, log, run = installation
    legacy = prepare_legacy(env)
    original = {str(p.relative_to(legacy)): p.read_bytes() for p in legacy.rglob("*") if p.is_file()}
    result = run("install")
    assert result.returncode == 0, result.stderr + result.stdout
    assert (root / ".env").read_bytes() == (legacy / ".env").read_bytes()
    assert (root / ".state/runtime").read_text().strip() == str(legacy)
    assert (root / ".state/project").read_text().strip() == "off-local-api"
    assert (root / ".state/previous").read_text().strip() == "legacy"
    assert not (root / "data").exists()
    assert original == {str(p.relative_to(legacy)): p.read_bytes() for p in legacy.rglob("*") if p.is_file()}
    calls = docker_calls(log)
    assert all(call[call.index("--project-directory") + 1] == str(legacy)
               for call in calls if "--project-directory" in call)
    result = run("rollback")
    assert result.returncode == 0, result.stderr + result.stdout
    assert (root / ".state/current").read_text().strip() == "legacy"
    assert (root / "off-proxy").exists()
    assert (legacy / "data/database").read_bytes() == original["data/database"]


def test_active_import_defers_migration_without_stopping_services(installation):
    root, env, log, run = installation
    prepare_legacy(env)
    result = run("install", FAKE_BUSY="1")
    assert result.returncode != 0
    assert "Update deferred" in result.stderr
    assert not any("stop" in call or "up" in call for call in docker_calls(log))


def test_update_preserves_configuration_and_rolls_back(installation):
    root, env, log, run = installation
    assert run("install").returncode == 0
    config = (root / ".env").read_bytes()
    result = run("update", FAKE_RELEASE="b" * 40)
    assert result.returncode == 0, result.stderr
    assert (root / ".state/current").read_text().strip() == "b" * 40
    assert (root / ".env").read_bytes() == config
    assert run("rollback").returncode == 0
    assert (root / ".state/current").read_text().strip() == "a" * 40


def test_failed_build_leaves_old_services_running(installation):
    root, env, log, run = installation
    assert run("install").returncode == 0
    log.write_text("")
    result = run("update", FAKE_RELEASE="b" * 40, FAKE_BUILD_FAIL="1")
    assert result.returncode != 0
    assert (root / ".state/current").read_text().strip() == "a" * 40
    assert not any("stop" in call or "up" in call for call in docker_calls(log))


def test_failed_api_restores_old_services(installation):
    root, env, log, run = installation
    assert run("install").returncode == 0
    log.write_text("")
    result = run("update", FAKE_RELEASE="b" * 40, FAKE_BAD_RELEASE="b" * 40)
    assert result.returncode != 0
    assert "restoring previous" in result.stderr
    assert (root / ".state/current").read_text().strip() == "a" * 40
    up_calls = [call for call in docker_calls(log) if "up" in call]
    assert len(up_calls) == 2
    assert "a" * 40 in up_calls[-1][up_calls[-1].index("-f") + 1]


def test_update_during_import_does_not_fetch_or_stop(installation):
    root, env, log, run = installation
    assert run("install").returncode == 0
    log.write_text("")
    result = run("update", FAKE_BUSY="1", FAKE_RELEASE="b" * 40)
    assert result.returncode != 0
    assert not (root / "releases" / ("b" * 40)).exists()
    assert not any("stop" in call for call in docker_calls(log))


def test_stop_down_and_product_argument_validation(installation):
    root, env, log, run = installation
    assert run("install").returncode == 0
    assert run("stop").returncode == 0
    assert run("down").returncode == 0
    assert (root / ".env").exists()
    assert run("test", "0000527000057", "beauty").returncode == 0
    assert run("test", "bad;anything").returncode != 0
    assert run("test", "12345678", "wrong").returncode != 0


def test_unknown_existing_directory_is_not_overwritten(installation):
    root, env, log, run = installation
    root.mkdir()
    (root / "unrelated").write_bytes(b"do not touch")
    assert run("install").returncode != 0
    assert list(root.iterdir()) == [root / "unrelated"]


def test_secrets_and_data_excluded_from_source_control():
    patterns = (SOURCE / ".gitignore").read_text().splitlines()
    assert all(name in patterns for name in (".env", "data/", "configdb/", "releases/", ".state/"))


def test_password_is_entered_twice_in_terminal_and_sent_only_on_stdin(installation):
    import pty
    import select
    import signal
    import time
    root, env, log, run = installation
    assert run('install').returncode == 0
    password = 'a-secret-typed-in-terminal'
    child, terminal = pty.fork()
    if child == 0:
        os.execve('/bin/bash', ['bash', str(SOURCE/'off-proxy'), 'password'], env)
    output = b''
    sent = 0
    done = False
    try:
        deadline = time.monotonic()+15
        while time.monotonic() < deadline:
            readable, _, _ = select.select([terminal], [], [], 0.1)
            if readable:
                try:
                    part = os.read(terminal, 4096)
                except OSError:
                    break
                if not part:
                    break
                output += part
                if sent == 0 and b'Neues GUI-Passwort' in output:
                    os.write(terminal, (password+'\n').encode()); sent = 1
                if sent == 1 and b'Passwort wiederholen:' in output:
                    os.write(terminal, (password+'\n').encode()); sent = 2
            ended, status = os.waitpid(child, os.WNOHANG)
            if ended:
                done = True
                assert os.waitstatus_to_exitcode(status) == 0, output.decode(errors='replace')
                break
        if not done:
            ended, status = os.waitpid(child, os.WNOHANG)
            if ended:
                done = True
                assert os.waitstatus_to_exitcode(status) == 0, output.decode(errors='replace')
        assert done and sent == 2, output.decode(errors='replace')
        assert password.encode() not in output
        assert password not in log.read_text()
        assert Path(str(log)+'.password-length').read_text() == str(len(password))
    finally:
        os.close(terminal)
        if not done:
            os.kill(child, signal.SIGKILL)
            os.waitpid(child, 0)
