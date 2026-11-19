"""Opt-in end-to-end management test; uses only an isolated temporary installation.

Run as root with DOCKER_SMOKE=1 on a disposable Docker host. Downloads are
replaced with local source archives; Docker, Compose, MongoDB and HTTP are real.
No external OFF exports are downloaded.
"""
import io
import os
from pathlib import Path
import subprocess
import tarfile
import time

import pytest

from test_security import Client

pytestmark = pytest.mark.skipif(os.environ.get('DOCKER_SMOKE') != '1', reason='explicit disposable Docker host required')
SOURCE = Path(__file__).parent


def test_real_install_update_rotation_and_rollback(tmp_path):
    assert os.geteuid() == 0
    root, tools, remote = tmp_path/'installed', tmp_path/'tools', tmp_path/'remote'
    tools.mkdir(); remote.mkdir()
    version = (SOURCE/'VERSION').read_text().strip()
    newer = version.rsplit('.', 1)[0]+'.'+str(int(version.rsplit('.', 1)[1])+1)
    for commit, target_version in [('a'*40, version), ('b'*40, newer)]:
        with tarfile.open(remote/(commit+'.tar.gz'), 'w:gz') as archive:
            for name in ('app.py','control.py','dashboard.py','security.py','components.py','VERSION','compose.yaml','Dockerfile','.dockerignore','requirements.txt','off-proxy','web/index.html','web/dashboard.js','web/dashboard.css'):
                body = (SOURCE/name).read_bytes()
                if name in ('app.py','VERSION'):
                    body = body.replace(version.encode(), target_version.encode())
                entry = tarfile.TarInfo('source/'+name)
                entry.size, entry.mode = len(body), 0o755 if name == 'off-proxy' else 0o644
                archive.addfile(entry, io.BytesIO(body))
    curl = tools/'curl'
    curl.write_text('''#!/usr/bin/env python3
import json,os,pathlib,shutil,sys
args=sys.argv[1:];dest=pathlib.Path(args[args.index('-o')+1]);url=next(a for a in args if a.startswith('https://'))
if 'api.github.com' in url:dest.write_text(json.dumps({'sha':os.environ['SMOKE_COMMIT']},indent=2))
else:shutil.copyfile(pathlib.Path(os.environ['SMOKE_ARCHIVES'])/(os.environ['SMOKE_COMMIT']+'.tar.gz'),dest)
''')
    curl.chmod(0o755)
    env = dict(os.environ, PATH=str(tools)+os.pathsep+os.environ['PATH'],
               OFF_PROXY_DIR=str(root), OFF_PROXY_BIN_DIR=str(tmp_path/'bin'),
               OFF_PROXY_LEGACY_DIR=str(tmp_path/'not-a-legacy-install'),
               OFF_PROXY_DISABLE_HOST_AGENT='1', SMOKE_COMMIT='a'*40, SMOKE_ARCHIVES=str(remote))
    def manage(*args, commit='a'*40):
        result = subprocess.run(['bash', str(SOURCE/'off-proxy'), *args], env=dict(env, SMOKE_COMMIT=commit),
                                text=True, capture_output=True, timeout=300)
        assert result.returncode == 0, result.stdout+'\n'+result.stderr
        return result
    def compose(*args, data=None):
        commit = (root/'.state/current').read_text().strip() if (root/'.state/current').exists() else 'a'*40
        return subprocess.run(['docker','compose','--project-directory',str(root),'--env-file',str(root/'.env'),
            '-p','off-proxy-server','-f',str(root/'releases'/commit/'compose.yaml'),*args],
            env=dict(env, OFF_PROXY_SOURCE_DIR=str(root/'releases'/commit),
                     OFF_PROXY_IMAGE_TAG=(root/'.state'/('image-'+commit)).read_text().strip() if (root/'.state'/('image-'+commit)).exists() else commit,
                     OFF_PROXY_MONGO_IMAGE=(root/'.state/mongo-image').read_text().strip() if (root/'.state/mongo-image').exists() else 'mongo:8.0'),
            input=data, text=True, capture_output=True, check=True, timeout=120)
    def wait_idle(client):
        for _ in range(75):
            if client.call('/ui/status')[1]['scheduler']['phase'] != 'running':
                return
            time.sleep(0.2)
        raise AssertionError('worker did not become idle')
    agent = None
    try:
        manage('install')
        initial_env = (root/'.env').read_bytes()
        token = next(line.split('=',1)[1] for line in initial_env.decode().splitlines() if line.startswith('API_TOKEN='))
        client = Client('http://127.0.0.1:8097')
        assert client.call('/auth/status')[1]['configured'] is False
        assert client.call('/ui/status')[0] == 401
        compose('exec','-T','api','python','app.py','password',data='eight888\n')
        assert client.login('eight888')[0] == 200
        rotated = 'docker-smoke-rotated-key-12345678'
        assert client.call('/ui/security', {'api_token':rotated})[0] == 200
        # Keep initial datasets unapproved, so the smoke test never fetches OFF data.
        compose('exec','-T','api','python','-c', 'from app import database,save_product; db=database(); save_product(db.food_smoke,{"code":"0123456789012","product_name":"Preserved smoke product"})')
        manage('status'); wait_idle(client)
        compose('stop','api')  # Update must recover even when the old API is unavailable.
        manage('update',commit='b'*40)
        assert (root/'.env').read_bytes() == initial_env
        assert client.call('/health', key=rotated)[1]['version'] == newer
        assert client.call('/health', key=token)[0] == 401
        assert client.call('/ui/status')[0] == 200  # Session survived replacement.
        wait_idle(client)
        source_before = (root/'.state/current').read_text()
        agent_log=(tmp_path/'agent.log').open('w')
        agent=subprocess.Popen(['bash',str(root/'off-proxy'),'components-worker'],env=env,stdout=agent_log,stderr=agent_log)
        for _ in range(60):
            if client.call('/ui/components')[1]['agent_available']: break
            time.sleep(.5)
        else: raise AssertionError('host agent did not become available')
        assert client.call('/ui/components')[1]['checked_at'] is None  # No automatic network checks.
        assert client.call('/ui/components/update', {'confirmed':True})[1]['queued'] is True
        deadline=time.monotonic()+300
        while time.monotonic() < deadline:
            try:
                state=client.call('/ui/components')[1]
                if state['status'] not in ('pending','running'):
                    assert state['status']=='success', state
                    break
            except (OSError, __import__('urllib.error',fromlist=['URLError']).URLError):
                pass  # Expected short outage while the API/MongoDB restart.
            time.sleep(1)
        else: raise AssertionError('GUI component update did not complete')
        assert len(state['rows']) == 3
        assert all(row['installed'] for row in state['rows'])
        job=state['job']
        time.sleep(6)
        assert client.call('/ui/components')[1]['job']==job  # No scheduled follow-up update.
        agent.terminate(); agent.wait(timeout=20); agent=None
        agent_log.close()
        assert (root/'.state/current').read_text() == source_before
        assert (root/'.env').read_bytes() == initial_env
        assert (root/'.state'/('image-'+'b'*40)).read_text().strip().startswith('b'*40+'-components-')
        assert client.call('/health', key=rotated)[1]['version'] == newer
        assert client.call('/health', key=token)[0] == 401
        assert client.call('/ui/status')[0] == 200
        wait_idle(client); manage('rollback')
        assert client.call('/health', key=rotated)[1]['version'] == version
        assert client.call('/ui/status')[0] == 200
        found = compose('exec','-T','api','python','-c','from app import database; print(database().food_smoke.find_one({"_id":"0123456789012"})["product"]["product_name"])')
        assert found.stdout.strip() == 'Preserved smoke product'
        assert compose('exec','-T','api','id','-u').stdout.strip() == '65532'
        # API lookup works when a published pointer is provided, without external fetches.
        compose('stop','sync')
        compose('exec','-T','api','python','-c','from app import database; database().state.update_one({"_id":"food"},{"$set":{"ready":True,"collection":"food_smoke"}},upsert=True)')
        assert client.call('/api/v3/product/0123456789012.json', key=rotated)[0] == 200
        manage('update')  # Same version: does not restart/import.
        assert (root/'.env').read_bytes() == initial_env
    except Exception:
        if (root/'.env').exists() and (root/'releases'/('a'*40)/'compose.yaml').exists():
            diagnostic = compose('logs','--tail','80','api','sync')
            print(diagnostic.stdout, diagnostic.stderr)
        raise
    finally:
        if agent is not None:
            agent.terminate(); agent.wait(timeout=20)
        if (root/'.env').exists() and (root/'releases'/('a'*40)/'compose.yaml').exists():
            compose('down')
