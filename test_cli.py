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
               OFF_PROXY_DISABLE_HOST_AGENT='1', FAKE_REMOTE=str(remote), FAKE_SOURCE=str(SOURCE), FAKE_LOG=str(log), FAKE_RELEASE="a" * 40)
    programs = {
        "id": "#!/bin/sh\necho 0\n",
        "sleep": "#!/bin/sh\nexit 0\n",
        "curl": '''#!/usr/bin/env python3
import json,os,pathlib,shutil,sys
args=sys.argv[1:];dest=pathlib.Path(args[args.index('-o')+1]);url=next(a for a in args if a.startswith('https://'))
with open(os.environ['FAKE_LOG']+'.downloads','a') as f:f.write(url+'\\n')
if 'codeload.github.com' in url and os.environ.get('FAKE_FETCH_FAIL')=='1':sys.exit(22)
if 'raw.githubusercontent.com' in url:shutil.copyfile(pathlib.Path(os.environ['FAKE_SOURCE'])/'off-proxy',dest)
elif 'api.github.com' in url:dest.write_text(json.dumps({'sha':os.environ['FAKE_RELEASE']},indent=2))
else:shutil.copyfile(pathlib.Path(os.environ['FAKE_REMOTE'])/(os.environ['FAKE_RELEASE']+'.tar.gz'),dest)
''',
        "docker": '''#!/usr/bin/env python3
import json,os,pathlib,sys
a=sys.argv[1:]
with open(os.environ['FAKE_LOG'],'a') as f:f.write(json.dumps(a)+'\\n')
with open(os.environ['FAKE_LOG']+'.images','a') as f:f.write(json.dumps([a,os.environ.get('OFF_PROXY_IMAGE_TAG'),os.environ.get('OFF_PROXY_MONGO_IMAGE')])+'\\n')
if a[:2]==['compose','version'] or a[:1]==['ps']:sys.exit(0)
if a[:1]==['inspect']:
    print('sha256:'+'a'*64);sys.exit(0)
if a[:2]==['image','inspect']:
    print(('python@sha256:' if 'python' in a[-1] else 'mongo@sha256:')+'b'*64 if 'RepoDigests' in a[3] else 'sha256:'+'a'*64)
    sys.exit(0)
if a[:1]==['pull']:sys.exit(1 if os.environ.get('FAKE_PULL_FAIL')=='1' else 0)
if '-f' not in a:sys.exit(9)
source=a[a.index('-f')+1]
if 'ps' in a:
    if os.environ.get('FAKE_RUNNING','1')=='1':print('existing-worker')
    sys.exit(0)
if 'exec' in a and any('result=db.scheduler.update_one' in x for x in a) and os.environ.get('FAKE_MAINTENANCE_BUSY')=='1':sys.exit(75)
if 'exec' in a and any('busy=' in x for x in a):sys.exit(75 if os.environ.get('FAKE_BUSY')=='1' else 0)
if 'exec' in a and any('sys.argv[1]' in x for x in a):
    sys.exit(1 if os.environ.get('FAKE_BAD_RELEASE','@') in source or (os.environ.get('FAKE_COMPONENT_FAIL')=='1' and 'components-' in os.environ.get('OFF_PROXY_IMAGE_TAG','')) else 0)
if 'build' in a:
    directory=pathlib.Path(source).parent
    if 'components.py' in (directory/'Dockerfile').read_text() and not (directory/'components.py').is_file():
        print('components.py: not found',file=sys.stderr);sys.exit(1)
    if os.environ.get('FAKE_BUILD_FAIL')=='1':sys.exit(1)
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
            for name in ("app.py", "dashboard.py", "control.py", "security.py", "components.py", "runtime-files.txt", "web/index.html", "web/dashboard.css", "web/dashboard.js", "VERSION", "compose.yaml", "Dockerfile", ".dockerignore", "requirements.txt", "off-proxy", "test_app.py", "requirements-dev.txt", ".github/workflows/test.yml"):
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
    password = 'eight888'
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


def test_runtime_install_excludes_tests_and_development_files(installation):
    root, env, log, run = installation
    assert run('install').returncode == 0
    source = root/'releases'/('a'*40)
    assert not list(source.glob('test*'))
    assert not (source/'test_app.py').exists()
    assert not (source/'requirements-dev.txt').exists()
    assert not (source/'.github').exists()
    assert (source/'security.py').is_file()
    for module in ('app.py','security.py','control.py','dashboard.py'):
        assert (source/module).stat().st_mode & 0o044 == 0o044
    assert (source/'web/index.html').stat().st_mode & 0o044 == 0o044
    assert (source/'web').stat().st_mode & 0o011 == 0o011


def test_bootstrap_pins_cli_and_archive_to_one_commit(installation):
    root, env, log, run = installation
    result = subprocess.run(['bash', str(SOURCE/'install.sh')], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    downloads = Path(str(log)+'.downloads').read_text().splitlines()
    assert sum('commits/main' in url for url in downloads) == 1
    assert any('/'+('a'*40)+'/off-proxy' in url for url in downloads)
    assert downloads[-1].endswith('/'+('a'*40))
    assert (root/'.state/current').read_text().strip() == 'a'*40


def test_failed_download_leaves_installed_version_and_data_unchanged(installation):
    root, env, log, run = installation
    assert run('install').returncode == 0
    before = (root/'.env').read_bytes()
    log.write_text('')
    assert run('update', FAKE_RELEASE='b'*40, FAKE_FETCH_FAIL='1').returncode != 0
    assert (root/'.state/current').read_text().strip() == 'a'*40
    assert (root/'.env').read_bytes() == before
    assert not any('stop' in call for call in docker_calls(log))


def test_racing_cycle_defers_update_after_build_before_stop(installation):
    root, env, log, run = installation
    assert run('install').returncode == 0
    log.write_text('')
    result = run('update', FAKE_RELEASE='b'*40, FAKE_MAINTENANCE_BUSY='1')
    assert result.returncode != 0
    assert 'deferred' in result.stderr
    calls = docker_calls(log)
    assert any('build' in call for call in calls)
    assert not any('stop' in call for call in calls)
    assert (root/'.state/current').read_text().strip() == 'a'*40


def test_gate_is_acquired_before_stop_and_released_after_success_or_restore(installation):
    root, env, log, run = installation
    assert run('install').returncode == 0
    for bad in ('@', 'b'*40):
        log.write_text('')
        result = run('update', FAKE_RELEASE='b'*40, FAKE_BAD_RELEASE=bad)
        calls = docker_calls(log)
        gate = next(i for i, c in enumerate(calls) if any('result=db.scheduler.update_one' in x for x in c))
        stop = next(i for i, c in enumerate(calls) if 'stop' in c)
        release = next(i for i, c in enumerate(calls) if any('$unset' in x and 'maintenance_until' in x for x in c))
        assert gate < stop < release
        if bad == '@':
            assert result.returncode == 0
            assert run('rollback').returncode == 0
        else:
            assert result.returncode != 0


def test_stopped_stack_can_be_updated_without_a_running_api(installation):
    root, env, log, run = installation
    assert run('install').returncode == 0
    log.write_text('')
    assert run('update', FAKE_RELEASE='b'*40, FAKE_RUNNING='0').returncode == 0
    assert (root/'.state/current').read_text().strip() == 'b'*40
    assert not any(any('result=db.scheduler.update_one' in x for x in call) for call in docker_calls(log))


def test_components_update_rebuilds_current_source_only_and_pins_images(installation):
    root, env, log, run = installation
    assert run('install').returncode == 0
    config = (root/'.env').read_bytes()
    downloads = Path(str(log)+'.downloads').read_bytes()
    log.write_text('')
    result = run('components-update')
    assert result.returncode == 0, result.stderr + result.stdout
    assert (root/'.state/current').read_text().strip() == 'a'*40
    tag = (root/'.state'/('image-'+'a'*40)).read_text().strip()
    assert tag.startswith('a'*40+'-components-')
    assert (root/'.state/mongo-image').read_text().strip() == 'mongo@sha256:'+'b'*64
    assert (root/'.env').read_bytes() == config
    assert Path(str(log)+'.downloads').read_bytes() == downloads
    calls = docker_calls(log)
    build = next(i for i,c in enumerate(calls) if 'build' in c)
    stop = next(i for i,c in enumerate(calls) if 'stop' in c)
    assert '--pull' in calls[build] and '--no-cache' in calls[build]
    assert build < stop
    assert ['pull','mongo:8.0'] in calls
    assert not any('down' in c or '--volumes' in c for c in calls)
    log.write_text('')
    assert run('start').returncode == 0
    images = [json.loads(line) for line in Path(str(log)+'.images').read_text().splitlines()]
    assert images[-1][1:] == [tag, 'mongo@sha256:'+'b'*64]
    # Ordinary same-commit updates keep the refreshed images.
    assert run('update').returncode == 0
    assert (root/'.state'/('image-'+'a'*40)).read_text().strip() == tag


@pytest.mark.parametrize('failure', ['FAKE_PULL_FAIL','FAKE_BUILD_FAIL','FAKE_MAINTENANCE_BUSY','FAKE_BUSY'])
def test_component_preparation_failure_never_stops_services(installation, failure):
    root, env, log, run = installation
    assert run('install').returncode == 0
    config = (root/'.env').read_bytes()
    log.write_text('')
    assert run('components-update', **{failure:'1'}).returncode != 0
    assert not any('stop' in c or 'up' in c for c in docker_calls(log))
    assert not (root/'.state'/('image-'+'a'*40)).exists()
    assert (root/'.env').read_bytes() == config


def test_failed_components_activation_restores_exact_previous_images(installation):
    root, env, log, run = installation
    assert run('install').returncode == 0
    log.write_text('')
    result = run('components-update', FAKE_COMPONENT_FAIL='1')
    assert result.returncode != 0
    assert 'restoring previous images' in result.stderr
    images = [json.loads(line) for line in Path(str(log)+'.images').read_text().splitlines()]
    up = [row for row in images if 'up' in row[0]]
    assert 'components-' in up[-2][1]
    assert up[-1][1:] == ['a'*40, 'sha256:'+'a'*64]
    assert not (root/'.state'/('image-'+'a'*40)).exists()
    assert (root/'.state/mongo-image').read_text().strip() == 'sha256:'+'a'*64


def test_components_update_can_start_a_stopped_stack(installation):
    root, env, log, run = installation
    assert run('install').returncode == 0
    assert run('components-update', FAKE_RUNNING='0').returncode == 0
    assert (root/'.state'/('image-'+'a'*40)).exists()


def test_installer_sets_up_request_only_systemd_host_agent(installation):
    root, env, log, run = installation
    service_dir=root.parent/'units'
    systemctl=Path(env['PATH'].split(os.pathsep)[0])/'systemctl'
    systemctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$FAKE_LOG.systemd"\n')
    systemctl.chmod(0o755)
    result=run('install', OFF_PROXY_DISABLE_HOST_AGENT='0', OFF_PROXY_TEST_SYSTEMD='1', OFF_PROXY_SERVICE_DIR=str(service_dir))
    assert result.returncode == 0, result.stderr
    units=list(service_dir.glob('*.service'))
    assert len(units)==1
    content=units[0].read_text()
    assert 'components-worker' in content and 'NoNewPrivileges=true' in content
    assert 'OnCalendar' not in content and 'components-update' not in content
    assert not list(service_dir.glob('*.timer'))
    assert 'enable ' in Path(str(log)+'.systemd').read_text()
    assert 'restart ' in Path(str(log)+'.systemd').read_text()


def historical_updater(tmp_path):
    result=subprocess.run(['git','show','e17b3d613c415385bc64e0270fabe335c57fea86:off-proxy'],
                          cwd=SOURCE,capture_output=True,text=True)
    if result.returncode:
        pytest.skip('Historical updater requires repository history (CI fetch-depth: 0)')
    path=tmp_path/'off-proxy-0.1.10'
    path.write_text(result.stdout)
    return path


def test_actual_010_updater_failure_is_repaired_by_bootstrap(installation):
    root, env, log, run=installation
    assert run('install').returncode == 0
    before=(root/'.env').read_bytes()
    old=historical_updater(root.parent)
    result=subprocess.run(['bash',str(old),'update'],env=dict(env,FAKE_RELEASE='b'*40),capture_output=True,text=True)
    assert result.returncode != 0
    assert 'components.py' in result.stderr
    incomplete=root/'releases'/('b'*40)
    assert incomplete.is_dir() and not (incomplete/'components.py').exists()
    assert (root/'.state/current').read_text().strip() == 'a'*40
    assert (root/'.env').read_bytes()==before
    result=subprocess.run(['bash',str(SOURCE/'install.sh')],env=dict(env,FAKE_RELEASE='b'*40),capture_output=True,text=True)
    assert result.returncode == 0, result.stdout+result.stderr
    assert (incomplete/'components.py').is_file()
    assert (incomplete/'runtime-files.txt').is_file()
    assert (root/'.state/current').read_text().strip() == 'b'*40
    assert (root/'.env').read_bytes()==before
    assert run('update', FAKE_RELEASE='b'*40).returncode == 0


def test_manifest_transports_future_modules_without_updater_changes(installation):
    root, env, log, run=installation
    assert run('install').returncode == 0
    archive=Path(env['FAKE_REMOTE'])/('b'*40+'.tar.gz')
    with tarfile.open(archive,'r:gz') as source:
        files={m.name:source.extractfile(m).read() for m in source if m.isfile()}
    prefix='off-proxy-server-'+('b'*40)+'/'
    files[prefix+'runtime-files.txt']+=b'future_runtime.py\n'
    files[prefix+'future_runtime.py']=b'"""Future runtime module."""\n'
    with tarfile.open(archive,'w:gz') as target:
        for name,body in files.items():
            entry=tarfile.TarInfo(name);entry.size=len(body);entry.mode=0o644
            target.addfile(entry,io.BytesIO(body))
    assert run('update',FAKE_RELEASE='b'*40).returncode == 0
    assert (root/'releases'/('b'*40)/'future_runtime.py').is_file()
