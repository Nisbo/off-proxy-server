"""Exercise the actual shell installer/updater with a fake Docker/GitHub boundary."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

import pytest

from .test_support import runtime_entries

SOURCE = Path(__file__).resolve().parents[1]
STABLE_VERSION = (SOURCE / "VERSION").read_text().strip()
CURRENT_STABLE_RELEASE = f"{'a' * 40} {STABLE_VERSION}"
NEXT_STABLE_RELEASE = f"{'b' * 40} {STABLE_VERSION}"


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
               OFF_PROXY_DISABLE_HOST_AGENT='1', FAKE_REMOTE=str(remote), FAKE_SOURCE=str(SOURCE), FAKE_LOG=str(log), FAKE_RELEASE="a" * 40,
               FAKE_STABLE_TAG="v"+STABLE_VERSION)
    programs = {
        "id": "#!/bin/sh\necho 0\n",
        "sleep": "#!/bin/sh\nexit 0\n",
        "ip": """#!/bin/sh
printf '%s\n' '2: eth0 inet 192.0.2.10/24 scope global eth0' \
    '3: wg0 inet 198.51.100.20/24 scope global wg0' \
    '4: docker0 inet 172.17.0.1/16 scope global docker0'
""",
        "curl": '''#!/usr/bin/env python3
import json,os,pathlib,shutil,sys
args=sys.argv[1:];dest=pathlib.Path(args[args.index('-o')+1]);url=next(a for a in args if a.startswith('https://'))
with open(os.environ['FAKE_LOG']+'.downloads','a') as f:f.write(url+'\\n')
if 'codeload.github.com' in url and os.environ.get('FAKE_FETCH_FAIL')=='1':sys.exit(22)
if 'raw.githubusercontent.com' in url:shutil.copyfile(pathlib.Path(os.environ['FAKE_SOURCE'])/'off-proxy',dest)
elif url.endswith('/releases/latest'):
    if os.environ.get('FAKE_NO_STABLE')=='1':sys.exit(22)
    dest.write_text(json.dumps({'tag_name':os.environ['FAKE_STABLE_TAG']},indent=2))
elif 'api.github.com' in url:dest.write_text(json.dumps({'sha':os.environ['FAKE_RELEASE']},indent=2))
else:shutil.copyfile(pathlib.Path(os.environ['FAKE_REMOTE'])/(url.rsplit('/',1)[-1]+'.tar.gz'),dest)
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
if 'run' in a and 'releases.py' in a:
    if not os.environ.get('FAKE_PUBLISHED'):
        sys.exit('No published release in this channel / Kein veröffentlichtes Release in diesem Kanal.')
    print(os.environ['FAKE_PUBLISHED'])
    sys.exit(0)
source=a[a.index('-f')+1]
if 'config' in a or 'up' in a:
    bind_ip=os.environ['BIND_IP']
    overlay=pathlib.Path(a[a.index('-f',a.index('-f')+1)+1]).read_text() if a.count('-f')>1 else None
    with open(os.environ['FAKE_LOG']+'.binds','a') as f:f.write(json.dumps([a,bind_ip,overlay])+'\\n')
    if 'up' in a and bind_ip==os.environ.get('FAKE_BIND_FAILURE'):sys.exit(1)
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
if a[-2:]==['app.py','password-configured']:
    print('yes' if pathlib.Path(os.environ['FAKE_LOG']+'.password-length').exists() else 'no')
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

    def archive(release, version=None):
        with tarfile.open(remote / (release + ".tar.gz"), "w:gz") as tar:
            for name in (*runtime_entries(SOURCE), "tests/test_app.py", "tests/requirements-dev.txt", ".github/workflows/test.yml"):
                data = (version+"\n").encode() if name == "VERSION" and version else (SOURCE / name).read_bytes()
                info = tarfile.TarInfo("off-proxy-server-" + release + "/" + name)
                info.size = len(data)
                info.mode = 0o755 if name == "off-proxy" else 0o644
                tar.addfile(info, io.BytesIO(data))
    archive("a" * 40)
    archive("b" * 40)
    archive("c" * 40, "0.2.0-beta.1")

    def run(*args, **changes):
        runtime = dict(env, **changes)
        if args[0] == "install":
            runtime["OFF_PROXY_BOOTSTRAP_COMMIT"] = runtime["FAKE_RELEASE"]
        return subprocess.run(["bash", str(SOURCE / "off-proxy"), *args],
                              env=runtime, text=True, capture_output=True)
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
    result = run("update", FAKE_PUBLISHED=CURRENT_STABLE_RELEASE)
    assert result.returncode == 0, result.stderr
    assert "Already current" in result.stdout
    assert not any("stop" in call or "up" in call for call in docker_calls(log))
    assert (root / ".env").read_bytes() == secret


def test_update_preserves_managed_runtime_location(installation):
    root, _, log, run = installation
    assert run("install").returncode == 0
    data_dir = root.parent / "existing-runtime"
    data_dir.mkdir()
    (data_dir/"database").write_bytes(b"existing products")
    (root/".state/runtime").write_text(str(data_dir)+"\n")
    (root/".state/project").write_text("existing-project\n")
    settings = (root/".env").read_bytes()
    log.write_text("")
    result = run("update", FAKE_PUBLISHED=NEXT_STABLE_RELEASE)
    assert result.returncode == 0, result.stderr
    assert (root/".env").read_bytes() == settings
    assert (data_dir/"database").read_bytes() == b"existing products"
    for call in docker_calls(log):
        if "--project-directory" in call:
            assert call[call.index("--project-directory")+1] == str(data_dir)
            assert call[call.index("-p")+1] == "existing-project"


def test_update_preserves_configuration_and_rolls_back(installation):
    root, env, log, run = installation
    assert run("install").returncode == 0
    config = (root / ".env").read_bytes()
    result = run("update", FAKE_PUBLISHED=NEXT_STABLE_RELEASE)
    assert result.returncode == 0, result.stderr
    assert (root / ".state/current").read_text().strip() == "b" * 40
    assert (root / ".env").read_bytes() == config
    assert run("rollback").returncode == 0
    assert (root / ".state/current").read_text().strip() == "a" * 40


def test_failed_build_leaves_old_services_running(installation):
    root, env, log, run = installation
    assert run("install").returncode == 0
    log.write_text("")
    result = run("update", FAKE_PUBLISHED=NEXT_STABLE_RELEASE, FAKE_BUILD_FAIL="1")
    assert result.returncode != 0
    assert (root / ".state/current").read_text().strip() == "a" * 40
    assert not any("stop" in call or "up" in call for call in docker_calls(log))


def test_failed_api_restores_old_services(installation):
    root, env, log, run = installation
    assert run("install").returncode == 0
    log.write_text("")
    result = run("update", FAKE_PUBLISHED=NEXT_STABLE_RELEASE, FAKE_BAD_RELEASE="b" * 40)
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
    result = run("update", FAKE_BUSY="1", FAKE_PUBLISHED=NEXT_STABLE_RELEASE)
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


def run_in_terminal(env, args, replies):
    import pty
    import select
    import signal
    import time

    child, terminal = pty.fork()
    if child == 0:
        os.execve('/bin/bash', ['bash', str(SOURCE/'off-proxy'), *args], env)
    output = b''
    sent = 0
    done = False
    try:
        deadline = time.monotonic()+15
        while time.monotonic() < deadline:
            readable, _, _ = select.select([terminal], [], [], 0.1)
            if readable:
                try:
                    output += os.read(terminal, 4096)
                except OSError:
                    pass
                if sent < len(replies) and replies[sent][0] in output:
                    os.write(terminal, replies[sent][1]+b'\n')
                    sent += 1
            ended, status = os.waitpid(child, os.WNOHANG)
            if ended:
                done = True
                assert os.waitstatus_to_exitcode(status) == 0, output.decode(errors='replace')
                break
        assert done and sent == len(replies), output.decode(errors='replace')
        return output.decode()
    finally:
        os.close(terminal)
        if not done:
            os.kill(child, signal.SIGKILL)
            os.waitpid(child, 0)


def test_password_is_entered_twice_in_terminal_and_sent_only_on_stdin(installation):
    root, env, log, run = installation
    assert run('install').returncode == 0
    assert run('bind', 'all').returncode != 0
    password = b'eight888'
    output = run_in_terminal(env, ['password'], [
        (b'Neues GUI-Passwort', password), (b'Passwort wiederholen:', password),
        (b'Auswahl [a]:', b''),
    ])
    assert password.decode() not in output + log.read_text()
    assert Path(str(log)+'.password-length').read_text() == str(len(password))
    assert 'BIND_IP=0.0.0.0' in (root/'.env').read_text()
    assert 'http://192.0.2.10:8097/' in output and 'http://198.51.100.20:8097/' in output
    assert '172.17.0.1' not in output
    assert not (root/'.state/pending-bind').exists()


@pytest.mark.parametrize('choice,addresses', [
    (b'', ['0.0.0.0']),
    (b'l', ['127.0.0.1']),
    (b'2', ['198.51.100.20']),
    (b'1 2', ['192.0.2.10', '198.51.100.20']),
])
def test_interactive_install_offers_bilingual_binding_and_prints_links(installation, choice, addresses):
    root, env, log, _ = installation
    output = run_in_terminal(dict(env, OFF_PROXY_BOOTSTRAP_COMMIT='a'*40), ['install'], [
        (b'New GUI password', b'eight888'), (b'Repeat password', b'eight888'),
        (b'Auswahl [a]:', choice),
    ])
    assert 'All IPv4 addresses / Alle IPv4-Adressen' in output
    assert 'Local only / Nur lokal' in output
    assert 'Open in your browser / Im Browser öffnen' in output
    expected_links = ['127.0.0.1', '192.0.2.10', '198.51.100.20'] if not choice else addresses
    for address in expected_links:
        assert f'http://{address}:8097/' in output
    config = (root/'.env').read_text()
    assert f'BIND_IP={addresses[0]}\n' in config
    assert (f'BIND_EXTRA_IPS={addresses[-1]}\n' in config) == (len(addresses) > 1)
    up_calls = [item for item in docker_calls(Path(str(log)+'.binds')) if 'up' in item[0]]
    assert up_calls[0][1] == '127.0.0.1'
    if choice != b'l':
        assert up_calls[-1][0][-5:] == ['up', '-d', '--no-deps', '--no-build', 'api']
        assert up_calls[-1][1] == addresses[0]
    if len(addresses) > 1:
        assert "198.51.100.20:${PORT:-8097}:8080" in up_calls[-1][2]


def test_bind_preserves_settings_on_update_and_failed_rebind(installation):
    root, env, log, run = installation
    assert run('install').returncode == 0
    # Simulate a previously configured, existing installation.
    (root/'.state/pending-bind').unlink()
    with (root/'.env').open('a') as settings:
        settings.write('KEEP=existing\n')
    result = run('bind', '192.0.2.10', '198.51.100.20', '198.51.100.20')
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'http://192.0.2.10:8097/' in result.stdout
    assert 'http://198.51.100.20:8097/' in result.stdout
    saved = (root/'.env').read_bytes()
    assert b'KEEP=existing\n' in saved and b'BIND_EXTRA_IPS=198.51.100.20\n' in saved
    assert run('update', FAKE_PUBLISHED=NEXT_STABLE_RELEASE).returncode == 0
    assert (root/'.env').read_bytes() == saved
    assert run('rollback').returncode == 0
    assert (root/'.env').read_bytes() == saved
    result = run('bind', 'all', FAKE_BIND_FAILURE='0.0.0.0')
    assert result.returncode != 0, result.stdout
    assert 'vorherige Einstellung wird wiederhergestellt' in result.stderr
    assert (root/'.env').read_bytes() == saved
    assert (root/'.env').stat().st_mode & 0o777 == 0o600
    up_calls = [item for item in docker_calls(Path(str(log)+'.binds')) if 'up' in item[0]]
    assert [item[1] for item in up_calls[-2:]] == ['0.0.0.0', '192.0.2.10']
    assert run('bind', '999.1.1.1').returncode != 0
    assert (root/'.env').read_bytes() == saved
    output = run_in_terminal(env, ['bind'], [(b'Auswahl [beibehalten]', b'l')])
    assert '127.0.0.1:8097' in output
    assert b'BIND_EXTRA_IPS=' not in (root/'.env').read_bytes()


def test_runtime_install_excludes_tests_and_development_files(installation):
    root, env, log, run = installation
    assert run('install').returncode == 0
    source = root/'releases'/('a'*40)
    assert not (source/'tests').exists()
    assert not (source/'.github').exists()
    program = source/'server'
    assert (program/'security.py').is_file()
    for module in ('app.py','security.py','control.py','dashboard.py'):
        assert (program/module).stat().st_mode & 0o044 == 0o044
    assert (program/'web/index.html').stat().st_mode & 0o044 == 0o044
    assert (program/'web').stat().st_mode & 0o011 == 0o011


def test_bootstrap_pins_stable_cli_and_archive_to_one_commit(installation):
    root, env, log, _ = installation
    result = subprocess.run(["bash", str(SOURCE/"install.sh")], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    downloads = Path(str(log)+".downloads").read_text().splitlines()
    api = "https://api.github.com/repos/Nisbo/off-proxy-server"
    assert downloads == [
        api+"/releases/latest", api+"/commits/tags/"+env["FAKE_STABLE_TAG"],
        f"https://raw.githubusercontent.com/Nisbo/off-proxy-server/{'a'*40}/off-proxy",
        f"https://codeload.github.com/Nisbo/off-proxy-server/tar.gz/{'a'*40}",
    ]
    assert (root/".state/current").read_text().strip() == "a"*40


def test_bootstrap_without_stable_release_never_uses_main(installation):
    root, env, log, _ = installation
    result = subprocess.run(["bash", str(SOURCE/"install.sh")], env=dict(env, FAKE_NO_STABLE="1"),
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "Kein stabiles Release" in result.stderr
    assert not root.exists()
    assert not log.exists()
    assert Path(str(log)+".downloads").read_text().splitlines() == [
        "https://api.github.com/repos/Nisbo/off-proxy-server/releases/latest"]


def test_bootstrap_refuses_beta_and_mismatched_release_version(installation):
    root, env, log, _ = installation
    for tag, expected in [("v0.2.0-beta.1", "Invalid stable release tag"),
                          ("v9.0.0", "Release tag and packaged version differ")]:
        result = subprocess.run(["bash", str(SOURCE/"install.sh")], env=dict(env, FAKE_STABLE_TAG=tag),
                                capture_output=True, text=True)
        assert result.returncode != 0
        assert expected in result.stderr
        assert not (root/".state/current").exists()
    assert not any("up" in call for call in docker_calls(log))


def test_bootstrap_main_requires_an_explicit_argument(installation):
    root, env, log, _ = installation
    result = subprocess.run(["bash", str(SOURCE/"install.sh"), "--main", str(root)],
                            env=dict(env, FAKE_NO_STABLE="1"), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    downloads = Path(str(log)+".downloads").read_text().splitlines()
    assert downloads[0].endswith("/commits/main")
    assert not any(url.endswith("/releases/latest") for url in downloads)
    assert (root/".state/current").read_text().strip() == "a"*40


def test_update_beta_head_fetches_only_the_beta_branch(installation):
    root, _, log, run = installation
    assert run("install").returncode == 0
    result = run("update", "beta", "--head", FAKE_RELEASE="c"*40)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (root / ".state/current").read_text().strip() == "c"*40
    downloads = Path(str(log)+".downloads").read_text().splitlines()
    assert not any(url.endswith("/commits/main") for url in downloads)
    assert sum(url.endswith("/commits/beta") for url in downloads) == 1
    assert "0.2.0-beta.1 ready" in result.stdout


@pytest.mark.parametrize("channel, options", [("stable", ()), ("beta", ("beta",))])
def test_update_without_published_release_does_not_fetch_or_restart(installation, channel, options):
    root, _, log, run = installation
    assert run("install").returncode == 0
    downloads = Path(str(log)+".downloads")
    before = downloads.read_bytes()
    settings = (root/".env").read_bytes()
    log.write_text("")
    result = run("update", *options, FAKE_RELEASE="b"*40, FAKE_BUSY="1")
    assert result.returncode != 0
    assert "No published release in this channel" in result.stderr
    assert "Kein veröffentlichtes Release in diesem Kanal" in result.stderr
    assert (root/".state/current").read_text().strip() == "a"*40
    assert (root/".env").read_bytes() == settings
    assert downloads.read_bytes() == before
    assert [call[-3:] for call in docker_calls(log) if "-f" in call] == [["api", "releases.py", channel]]


def test_update_installs_stable_release_commit_instead_of_main_head(installation):
    root, _, log, run = installation
    assert run("install").returncode == 0
    result = run("update", FAKE_RELEASE="c"*40, FAKE_PUBLISHED=NEXT_STABLE_RELEASE)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (root/".state/current").read_text().strip() == "b"*40
    assert ["api", "releases.py", "stable"] in [call[-3:] for call in docker_calls(log)]
    downloads = Path(str(log)+".downloads").read_text().splitlines()
    assert not any("/commits/" in url for url in downloads)
    assert downloads[-1].endswith("/tar.gz/"+"b"*40)


def test_update_beta_installs_the_published_commit_and_requires_the_packaged_version(installation):
    root, _, log, run = installation
    assert run("install").returncode == 0
    assert run("update", "beta").returncode != 0
    assert run("update", "beta", FAKE_PUBLISHED="c"*40+" 0.2.0-beta.2").returncode != 0
    assert (root / ".state/current").read_text().strip() == "a"*40
    result = run("update", "beta", FAKE_PUBLISHED="c"*40+" 0.2.0-beta.1")
    assert result.returncode == 0, result.stderr + result.stdout
    assert (root / ".state/current").read_text().strip() == "c"*40
    assert ["api", "releases.py", "beta"] in [call[-3:] for call in docker_calls(log)]
    assert not any(url.endswith("/commits/beta") for url in Path(str(log)+".downloads").read_text().splitlines())


def test_host_program_update_requires_the_same_published_commit(installation):
    root, env, log, run = installation
    assert run("install").returncode == 0
    (root/"data"/"probe").write_text("product data")
    settings = (root/".env").read_bytes()
    assert run("program-release-install", "beta", "b"*40, "0.2.0-beta.1",
               FAKE_PUBLISHED="c"*40+" 0.2.0-beta.1").returncode == 76
    assert (root / ".state/current").read_text().strip() == "a"*40
    launcher = Path(env["OFF_PROXY_BIN_DIR"], "off-proxy")
    original_launcher = launcher.stat().st_ino
    result = run("program-release-install", "beta", "c"*40, "0.2.0-beta.1",
                 FAKE_PUBLISHED="c"*40+" 0.2.0-beta.1")
    assert result.returncode == 0, result.stderr + result.stdout
    assert (root / ".state/current").read_text().strip() == "c"*40
    assert (root / ".state/previous").read_text().strip() == "a"*40
    assert (root/".env").read_bytes() == settings
    assert (root/"data"/"probe").read_text() == "product data"
    assert launcher.stat().st_ino == original_launcher
    assert not (root/".state"/"components.log").exists()


def test_failed_download_leaves_installed_version_and_data_unchanged(installation):
    root, env, log, run = installation
    assert run('install').returncode == 0
    before = (root/'.env').read_bytes()
    log.write_text('')
    assert run('update', FAKE_PUBLISHED=NEXT_STABLE_RELEASE, FAKE_FETCH_FAIL='1').returncode != 0
    assert (root/'.state/current').read_text().strip() == 'a'*40
    assert (root/'.env').read_bytes() == before
    assert not any('stop' in call for call in docker_calls(log))


def test_racing_cycle_defers_update_after_build_before_stop(installation):
    root, env, log, run = installation
    assert run('install').returncode == 0
    log.write_text('')
    result = run('update', FAKE_PUBLISHED=NEXT_STABLE_RELEASE, FAKE_MAINTENANCE_BUSY='1')
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
        result = run('update', FAKE_PUBLISHED=NEXT_STABLE_RELEASE, FAKE_BAD_RELEASE=bad)
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
    assert run('update', FAKE_PUBLISHED=NEXT_STABLE_RELEASE, FAKE_RUNNING='0').returncode == 0
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
    assert run('update', FAKE_PUBLISHED=CURRENT_STABLE_RELEASE).returncode == 0
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


def test_manifest_transports_future_modules_without_updater_changes(installation):
    root, env, log, run=installation
    assert run('install').returncode == 0
    archive=Path(env['FAKE_REMOTE'])/('b'*40+'.tar.gz')
    with tarfile.open(archive,'r:gz') as source:
        files={m.name:source.extractfile(m).read() for m in source if m.isfile()}
    prefix='off-proxy-server-'+('b'*40)+'/'
    files[prefix+'server/runtime-files.txt']+=b'future_runtime.py\n'
    files[prefix+'server/future_runtime.py']=b'"""Future runtime module."""\n'
    with tarfile.open(archive,'w:gz') as target:
        for name,body in files.items():
            entry=tarfile.TarInfo(name);entry.size=len(body);entry.mode=0o644
            target.addfile(entry,io.BytesIO(body))
    assert run('update', FAKE_PUBLISHED=NEXT_STABLE_RELEASE).returncode == 0
    assert (root/'releases'/('b'*40)/'server'/'future_runtime.py').is_file()
