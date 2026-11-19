"""Administrator authentication, revocable sessions and persistent API credentials."""
import datetime as dt
import hashlib
import hmac
import re
import secrets
import threading
import time
from http.cookies import SimpleCookie, CookieError

from pymongo import ReturnDocument

COOKIE = 'off_proxy_session'
ITERATIONS = 600_000
MAX_AGE = 365 * 86400


class Denied(Exception):
    def __init__(self, code='authentication_required', status=401):
        self.code, self.status = code, status


def password_hash(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError('Password must contain 12–256 characters / Passwort muss 12–256 Zeichen enthalten')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f'pbkdf2-sha256${ITERATIONS}${salt}${digest}'


def password_matches(password, encoded):
    if not isinstance(password, str) or len(password) > 256 or not encoded:
        return False
    algorithm, rounds, salt, digest = encoded.split('$')
    if algorithm != 'pbkdf2-sha256':
        return False
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds)).hex()
    return hmac.compare_digest(actual, digest)


class Security:
    def __init__(self, db, bootstrap_token):
        self.db = db
        self.login_lock = threading.Lock()
        db.security.update_one({'_id': 'admin'}, {'$setOnInsert': {
            'password_hash': None, 'epoch': secrets.token_hex(16), 'idle_minutes': 30,
            'api_auth_required': True, 'api_token': bootstrap_token}}, upsert=True)
        db.sessions.create_index('expires_at', expireAfterSeconds=0)
        db.auth_limits.create_index('expires_at', expireAfterSeconds=0)

    def config(self):
        return self.db.security.find_one({'_id': 'admin'})

    def public_settings(self):
        config = self.config()
        return {k: config[k] for k in ('idle_minutes', 'api_auth_required')}

    def api_key(self):
        return self.config()['api_token']

    def set_password(self, password):
        encoded = password_hash(password)
        self.db.security.update_one({'_id': 'admin'}, {'$set': {
            'password_hash': encoded, 'epoch': secrets.token_hex(16)}})
        self.db.sessions.delete_many({})

    def limit_login(self, address):
        now = time.time()
        # Persistent fixed-window limits survive a restart. No untrusted proxy headers.
        for identity, limit in (('all', 60), (hashlib.sha256(address.encode()).hexdigest(), 8)):
            row = self.db.auth_limits.find_one_and_update({'_id': f'{identity}:{int(now // 300)}'}, {
                '$inc': {'attempts': 1}, '$setOnInsert': {'expires_at': dt.datetime.fromtimestamp(now+600, dt.timezone.utc)}},
                upsert=True, return_document=ReturnDocument.AFTER)
            if row['attempts'] > limit:
                raise Denied('login_limited', 429)

    def login(self, password, address):
        self.limit_login(address)
        if not self.login_lock.acquire(blocking=False):
            raise Denied('login_limited', 429)
        try:
            config = self.config()
            if not config['password_hash']:
                raise Denied('password_not_configured', 403)
            if not password_matches(password, config['password_hash']):
                raise Denied('invalid_password')
            if self.config()['epoch'] != config['epoch']:
                raise Denied('invalid_password')
            raw, csrf, now = secrets.token_urlsafe(32), secrets.token_urlsafe(32), time.time()
            self.db.sessions.insert_one({'_id': hashlib.sha256(raw.encode()).hexdigest(),
                'epoch': config['epoch'], 'csrf': csrf, 'last_seen': now, 'created': now,
                'expires_at': dt.datetime.fromtimestamp(now+MAX_AGE, dt.timezone.utc)})
            return raw
        finally:
            self.login_lock.release()

    def session(self, cookie_header):
        try:
            cookies = SimpleCookie(cookie_header or '')
            raw = cookies[COOKIE].value if COOKIE in cookies else ''
        except CookieError:
            return None
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', raw):
            return None
        row = self.db.sessions.find_one({'_id': hashlib.sha256(raw.encode()).hexdigest()})
        if not row:
            return None
        config, now = self.config(), time.time()
        minutes = config['idle_minutes']
        if (row['epoch'] != config['epoch'] or now-row['created'] >= MAX_AGE
                or (minutes and now-row['last_seen'] >= minutes*60)):
            self.db.sessions.delete_one({'_id': row['_id']})
            return None
        return row

    def activity(self, session):
        self.db.sessions.update_one({'_id': session['_id']}, {'$set': {'last_seen': time.time()}})

    def revoke_all(self):
        self.db.security.update_one({'_id': 'admin'}, {'$set': {'epoch': secrets.token_hex(16)}})
        self.db.sessions.delete_many({})

    def save(self, values):
        if set(values) - {'idle_minutes', 'api_auth_required', 'api_token', 'confirm_public_api'}:
            raise ValueError('Unknown security setting')
        update = {}
        if 'idle_minutes' in values:
            minutes = values['idle_minutes']
            if type(minutes) is not int or not 0 <= minutes <= 525600:
                raise ValueError('Invalid timeout')
            update['idle_minutes'] = minutes
        if 'api_auth_required' in values:
            required = values['api_auth_required']
            if type(required) is not bool:
                raise ValueError('Invalid API policy')
            if not required and self.config()['api_auth_required'] and values.get('confirm_public_api') is not True:
                raise ValueError('Public API requires confirmation')
            update['api_auth_required'] = required
        if 'api_token' in values:
            token = values['api_token']
            if not isinstance(token, str) or not re.fullmatch(r'[!-~]{24,256}', token):
                raise ValueError('API key must contain 24–256 non-space ASCII characters')
            update['api_token'] = token
        if update:
            self.db.security.update_one({'_id': 'admin'}, {'$set': update})
        return self.public_settings()
