"""Exercise the real Gunicorn master/worker HTTP boundary with disposable data."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest
from .test_security import Client


@pytest.fixture(scope='module')
def gunicorn(tmp_path_factory):
    root = tmp_path_factory.mktemp('gunicorn')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    runner = root/'runner.py'
    runner.write_text('''import app,mongomock
class TestServer(app.Gunicorn):
 def load_config(self):
  super().load_config()
  self.cfg.set('bind', '127.0.0.1:PORT')
 def load(self):
  db=mongomock.MongoClient().off_local
  service=app.Application(db,'existing-key-preserved-123456789')
  service.security.set_password('eight888')
  app.save_product(db.food_test,{'code':'000123','product_name':'Preserved product'})
  db.state.insert_one({'_id':'food','ready':True,'collection':'food_test'})
  return service.application
TestServer().run()
'''.replace('PORT',str(port)))
    log = (root/'server.log').open('w')
    source = Path(__file__).resolve().parents[1]
    process = subprocess.Popen([sys.executable,str(runner)], cwd=source,
        env=dict(os.environ, PYTHONPATH=str(source / "server")), stdout=log, stderr=log)
    client = Client(f'http://127.0.0.1:{port}')
    try:
        for _ in range(100):
            if process.poll() is not None:
                pytest.fail((root/'server.log').read_text())
            try:
                if client.call('/auth/status')[0] == 200:
                    break
            except (OSError, urllib.error.URLError):
                time.sleep(.1)
        else:
            pytest.fail('Gunicorn did not start')
        yield client
    finally:
        process.terminate()
        process.wait(timeout=35)
        log.close()


def test_real_gunicorn_login_rotation_and_gui_protection(gunicorn):
    client = gunicorn
    assert client.call('/ui/components')[0] == 401
    assert client.login('eight888')[0] == 200
    assert client.call('/ui/components')[1]['agent_available'] is False
    assert client.call('/ui/components/check', {})[0] == 503
    key='rotated-key-preserved-123456789'
    assert client.call('/ui/security', {'api_token':key})[0] == 200
    assert client.call('/api/v3/product/000123.json', key=key)[1]['product']['product_name'] == 'Preserved product'
    assert client.call('/api/v3/product/000123.json', key='existing-key-preserved-123456789')[0] == 401


@pytest.mark.parametrize('wire', [
    b'GET http://[ HTTP/1.0\r\nHost: localhost\r\n\r\n',
    b'POST /auth/login HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\nContent-Length: 3\r\n\r\n{}x',
])
def test_gunicorn_rejects_ambiguous_or_invalid_http(gunicorn, wire):
    from urllib.parse import urlsplit
    address = urlsplit(gunicorn.base)
    with socket.create_connection((address.hostname,address.port),timeout=5) as connection:
        connection.sendall(wire)
        response=connection.recv(1024)
        assert not response or b' 400 ' in response.split(b'\r\n',1)[0]
    assert gunicorn.call('/auth/status')[0] == 200


def test_gunicorn_rejects_oversized_json(gunicorn):
    request=urllib.request.Request(gunicorn.base+'/auth/login',data=b'x'*4097,
                                  headers={'Content-Type':'application/json'})
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request,timeout=5)
    assert caught.value.code == 413
