"""Authentication and access boundaries exercised through actual HTTP requests."""
import hashlib
import http.cookiejar
import json
import threading
import time
import urllib.error
import urllib.request
from unittest.mock import patch

import pytest

import app
import security
from test_app import db, publish

PASSWORD = 'a long test password äöü'
KEY = 'existing-key-preserved-123456789'


class Client:
    def __init__(self, base):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = None

    def call(self, path, body=None, key=None, headers=None):
        headers = dict(headers or {})
        if key is not None:
            headers['Authorization'] = 'Bearer ' + key
        if body is not None:
            headers['Content-Type'] = 'application/json'
            if self.csrf:
                headers.setdefault('X-Off-Proxy-Control', self.csrf)
        request = urllib.request.Request(self.base+path, data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            response = self.opener.open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response), response.headers

    def login(self, password=PASSWORD):
        self.csrf = self.call('/auth/status')[1]['control_nonce']
        result = self.call('/auth/login', {'password': password})
        if result[0] == 200:
            self.csrf = self.call('/auth/status')[1]['control_nonce']
        return result


@pytest.fixture
def secured(db):
    server = app.Server(('127.0.0.1', 0), db, KEY)
    server.security.set_password(PASSWORD)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, Client(f'http://127.0.0.1:{server.server_port}')
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.mark.parametrize('path', ['/ui/status','/ui/lookup?ean=4062139025398','/ui/security','/ui/api-key'])
def test_no_gui_data_without_login_even_with_api_key(secured, path):
    _, client = secured
    assert client.call(path)[0] == 401
    assert client.call(path, key=KEY)[0] == 401
    public = client.call('/auth/status')[1]
    assert set(public) == {'authenticated', 'configured', 'control_nonce'}
    assert public['authenticated'] is False
    assert KEY not in json.dumps(public)


@pytest.mark.parametrize('path', ['/ui/sync','/ui/settings','/ui/security','/ui/full-import','/auth/password','/auth/logout-all','/auth/activity'])
def test_mutations_require_session(secured, path):
    server, client = secured
    client.csrf = server.control_nonce
    assert client.call(path, {}, key=KEY)[0] == 401
    assert server.db.requests.count_documents({}) == 0


def test_first_setup_cannot_be_claimed_via_web(secured):
    server, client = secured
    server.db.security.update_one({'_id':'admin'}, {'$set': {'password_hash': None}})
    assert client.call('/auth/status')[1]['configured'] is False
    assert client.login()[0] == 403
    assert client.call('/auth/password', {'new_password':PASSWORD})[0] == 401
    assert server.security.api_key() == KEY
    publish(server.db)
    assert client.call('/api/v3/product/4062139025398.json', key=KEY)[0] == 200


def test_real_login_csrf_cookie_and_logout(secured):
    server, client = secured
    assert client.call('/auth/login', {'password':PASSWORD})[0] == 403
    assert client.login('incorrect password')[0] == 401
    status, _, headers = client.login()
    assert status == 200
    cookie = headers['Set-Cookie']
    assert 'HttpOnly' in cookie and 'SameSite=Strict' in cookie and 'Path=/' in cookie
    raw = next(iter(client.jar)).value
    assert server.db.sessions.find_one({'_id':hashlib.sha256(raw.encode()).hexdigest()})
    assert raw not in json.dumps(list(server.db.sessions.find({})), default=str)
    assert client.call('/ui/status')[0] == 200
    assert client.call('/ui/sync', {}, headers={'Origin':'https://unrelated.invalid'})[0] == 403
    assert client.call('/ui/sync', {}, headers={'X-Off-Proxy-Control':'bad'})[0] == 403
    assert client.call('/auth/logout', {})[0] == 200
    assert client.call('/ui/status')[0] == 401


def test_https_proxy_cookie_is_secure(secured):
    _, client = secured
    client.csrf = client.call('/auth/status')[1]['control_nonce']
    result = client.call('/auth/login', {'password':PASSWORD}, headers={'X-Forwarded-Proto':'https'})
    assert 'Secure' in result[2]['Set-Cookie']


def test_polling_does_not_extend_idle_timeout_and_setting_is_immediate(secured):
    server, client = secured
    client.login()
    client.call('/ui/security', {'idle_minutes':1})
    now = time.time()
    server.db.sessions.update_many({}, {'$set': {'last_seen':now-59}})
    assert client.call('/ui/status')[0] == 200
    assert client.call('/auth/status')[1]['authenticated'] is True
    assert server.db.sessions.find_one({})['last_seen'] == now-59
    with patch('security.time.time', return_value=now+2):
        assert client.call('/ui/status')[0] == 401
        assert client.call('/ui/sync', {})[0] == 401


def test_user_activity_extends_session_and_timeout_can_be_disabled(secured):
    server, client = secured
    client.login()
    client.call('/ui/security', {'idle_minutes':1})
    now = time.time()
    server.db.sessions.update_many({}, {'$set': {'last_seen':now-59}})
    assert client.call('/auth/activity', {})[0] == 200
    assert server.db.sessions.find_one({})['last_seen'] > now-1
    assert client.call('/ui/security', {'idle_minutes':0})[0] == 200
    server.db.sessions.update_many({}, {'$set': {'last_seen':now-86400}})
    assert client.call('/ui/status')[0] == 200


def test_password_change_requires_current_password_and_revokes_all_sessions(secured):
    server, first = secured
    second = Client(first.base)
    first.login(); second.login()
    assert first.call('/auth/password', {'current_password':'wrong','new_password':'new strong password'})[0] == 401
    assert second.call('/ui/status')[0] == 200
    assert first.call('/auth/password', {'current_password':PASSWORD,'new_password':'new strong password'})[0] == 200
    assert first.call('/ui/status')[0] == second.call('/ui/status')[0] == 401
    assert first.login()[0] == 401
    assert first.login('new strong password')[0] == 200
    assert server.security.api_key() == KEY


def test_logout_all_revokes_other_browser(secured):
    _, first = secured
    second = Client(first.base)
    first.login(); second.login()
    assert first.call('/auth/logout-all', {})[0] == 200
    assert first.call('/ui/status')[0] == second.call('/ui/status')[0] == 401


def test_shell_password_reset_invalidates_existing_sessions(secured):
    server, client = secured
    client.login()
    server.security.set_password('a password from the terminal')
    assert client.call('/ui/status')[0] == 401
    assert client.login('a password from the terminal')[0] == 200


def test_api_rotation_reveal_and_restart_preserve_key_and_data(secured):
    server, client = secured
    publish(server.db)
    before = server.db.state.find_one({'_id':'food'})
    client.login()
    assert client.call('/ui/api-key')[0] == 403
    assert client.call('/ui/api-key', headers={'X-Off-Proxy-Control':client.csrf})[1]['api_token'] == KEY
    for path in ('/ui/status','/ui/security','/auth/status'):
        assert KEY not in json.dumps(client.call(path)[1])
    new_key = 'changed-api-key-123456789012345'
    assert client.call('/ui/security', {'api_token':new_key})[0] == 200
    assert client.call('/api/v3/product/4062139025398.json', key=KEY)[0] == 401
    assert client.call('/api/v3/product/4062139025398.json', key=new_key)[0] == 200
    assert client.call('/health', key=new_key)[0] == 200
    restarted = security.Security(server.db, 'different-bootstrap-key-must-not-overwrite')
    assert restarted.api_key() == new_key
    assert restarted.public_settings()['api_auth_required'] is True
    assert server.db.state.find_one({'_id':'food'}) == before
    assert server.security.session(f'{security.COOKIE}={next(iter(client.jar)).value}')


def test_public_product_api_is_explicit_and_does_not_unlock_gui_or_health(secured):
    server, client = secured
    publish(server.db)
    client.login()
    assert client.call('/ui/security', {'api_auth_required':False})[0] == 400
    assert client.call('/ui/security', {'api_auth_required':False,'confirm_public_api':True})[0] == 200
    public = Client(client.base)
    assert public.call('/api/v3/product/4062139025398.json')[0] == 200
    assert public.call('/health')[0] == public.call('/ui/status')[0] == public.call('/ui/lookup?ean=4062139025398')[0] == 401
    assert client.call('/ui/security', {'api_auth_required':True})[0] == 200
    assert public.call('/api/v3/product/4062139025398.json')[0] == 401


@pytest.mark.parametrize('values', [{'idle_minutes':True},{'idle_minutes':-1},{'idle_minutes':0.5},{'api_token':'short'},{'api_token':'with spaces in a long secret'},{'api_auth_required':0},{'password_hash':'bad'}])
def test_invalid_security_settings_do_not_change_key(secured, values):
    server, client = secured
    client.login()
    assert client.call('/ui/security', values)[0] == 400
    assert server.security.api_key() == KEY


def test_rate_limit_survives_service_object_restart(secured):
    server, client = secured
    for _ in range(8):
        assert client.login('wrong password')[0] == 401
    assert client.login()[0] == 429
    server.security = security.Security(server.db, KEY)
    assert client.login()[0] == 429


def test_password_is_salted_hash_and_never_plaintext(secured):
    server, _ = secured
    first = server.security.config()['password_hash']
    assert first.startswith('pbkdf2-sha256$600000$')
    assert PASSWORD not in first and PASSWORD not in json.dumps(server.security.config())
    assert security.password_matches(PASSWORD, first)
    server.security.set_password(PASSWORD)
    assert server.security.config()['password_hash'] != first


def test_login_form_never_submits_password_in_url_if_javascript_fails(secured):
    from html.parser import HTMLParser
    _, client = secured
    class Forms(HTMLParser):
        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag == 'form' and values.get('id') == 'login-form':
                assert values.get('method') == 'post'
                assert values.get('action') == '/auth/login'
                self.found = True
    with client.opener.open(client.base+'/') as response:
        parser = Forms()
        parser.feed(response.read().decode())
    assert parser.found
