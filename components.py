"""Authenticated, explicit component jobs; no Docker access from the web process."""
import importlib.metadata
import json
import re
import secrets
import sys
import time
import urllib.parse
import urllib.request

from pymongo import ReturnDocument
import security

ACTIVE = ('pending', 'running')
DIGEST = re.compile(r'^(?:python|mongo)@sha256:[a-f0-9]{64}$')


def snapshot(db):
    state = db.components.find_one({'_id': 'host'}) or {}
    return {key: state.get(key) for key in ('status', 'action', 'job', 'phase', 'checked_at', 'finished_at', 'result', 'rows', 'installed', 'target')} | {
        'agent_available': time.time() - state.get('heartbeat', 0) < 30,
        'agent_version': state.get('agent_version'),
    }


def request(db, action, *, reinstall=False, target=None):
    if action not in ('check', 'update', 'program-update'):
        raise ValueError('Unsupported component action')
    state = snapshot(db)
    if not state['agent_available']:
        raise security.Denied('component_agent_unavailable', 503)
    if action in ('update', 'program-update') and db.scheduler.find_one({'_id': 'sync', 'phase': 'running'}):
        raise security.Denied('component_import_active', 409)
    all_current = all(any(row.get('name') == name and row.get('state') == 'current'
                          for row in (state.get('rows') or [])) for name in ('python', 'gunicorn', 'mongo'))
    if action == 'update' and not reinstall and state['status'] not in ACTIVE and all_current:
        raise security.Denied('components_already_current', 409)
    db.components.update_one({'_id': 'host'}, {'$setOnInsert': {'status': 'idle'}}, upsert=True)
    result = db.components.update_one({'_id': 'host', 'status': {'$nin': ACTIVE}},
        {'$set': {'status': 'pending', 'action': action, 'job': secrets.token_hex(16),
                  'requested_at': time.time(), 'phase': 'pending', 'result': None, 'target': target}})
    return bool(result.modified_count)


def heartbeat(db):
    from app import VERSION
    db.components.update_one({'_id': 'host'}, {'$set': {'heartbeat': time.time(), 'agent_version': VERSION},
                            '$setOnInsert': {'status': 'idle'}}, upsert=True)


def claim(db):
    now = time.time()
    db.components.update_one({'_id': 'host', 'status': 'pending', 'requested_at': {'$lt': now-300}},
                             {'$set': {'status': 'failed', 'result': 'expired', 'finished_at': now}})
    state = db.components.find_one_and_update({'_id': 'host', 'status': 'pending', 'action': {'$in': ['check', 'update', 'program-update']}},
        {'$set': {'status': 'running', 'phase': 'preparing'}}, return_document=ReturnDocument.AFTER)
    if not state:
        return ''
    if state['action'] == 'program-update':
        # The shell validates all three fields before using them.
        target = state.get('target') or {}
        return ' '.join(('program-update', target['channel'], target['commit'], target['version']))
    return state['action']


def inventory(db, base, mongo):
    # Only identifiers are stored, never host paths, credentials or raw command output.
    base = base if DIGEST.fullmatch(base) and base.startswith('python@') else None
    mongo = mongo if DIGEST.fullmatch(mongo) and mongo.startswith('mongo@') else None
    installed = {
        'python': {'version': sys.version.split()[0], 'digest': base},
        'gunicorn': {'version': importlib.metadata.version('gunicorn')},
        'mongo': {'version': db.client.server_info()['version'], 'digest': mongo},
    }
    previous = (db.components.find_one({'_id': 'host'}) or {}).get('installed')
    values = {'installed': installed}
    if previous != installed:
        values.update(rows=[], checked_at=None)
    db.components.update_one({'_id': 'host'}, {'$set': values}, upsert=True)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Update sources must not redirect')


def open_https(request):
    parsed = urllib.parse.urlsplit(request.full_url)
    if (parsed.scheme != 'https' or parsed.hostname not in ('pypi.org', 'auth.docker.io', 'registry-1.docker.io', 'hub.docker.com', 'api.github.com')
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError('Unsupported update source')
    return urllib.request.build_opener(NoRedirect()).open(request, timeout=15)


def json_url(url, headers=None):
    request = urllib.request.Request(url, headers={'User-Agent': 'OFF-Proxy-Server/0.1.11', **(headers or {})})
    with open_https(request) as response:
        if not response.url.startswith('https://'):
            raise ValueError('HTTPS required')
        body = response.read(4*1024*1024+1)
        if len(body) > 4*1024*1024:
            raise ValueError('Response too large')
        return json.loads(body)


def registry_digest(repository, tag):
    token = json_url('https://auth.docker.io/token?' + urllib.parse.urlencode({
        'service': 'registry.docker.io', 'scope': f'repository:library/{repository}:pull'}))['token']
    request = urllib.request.Request(f'https://registry-1.docker.io/v2/library/{repository}/manifests/{tag}', method='HEAD', headers={
        'Authorization': 'Bearer '+token,
        'Accept': 'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json'})
    with open_https(request) as response:
        digest = response.headers.get('Docker-Content-Digest', '')
    result = repository+'@'+digest
    if not DIGEST.fullmatch(result):
        raise ValueError('Invalid registry digest')
    return result


def registry_version(repository, tag, digest):
    """Find a versioned tag pointing at the exact image checked by the updater."""
    series = {'python': '3.13', 'mongo': '8.0'}[repository]
    suffix = '-slim' if tag.endswith('-slim') else ''
    pattern = re.compile(rf'({re.escape(series)}\.[0-9]+){suffix}')
    query = urllib.parse.urlencode({'name': series, 'page_size': 100})
    data = json_url(f'https://hub.docker.com/v2/namespaces/library/repositories/{repository}/tags?{query}')
    image_digest = digest.split('@', 1)[1]
    for row in data['results']:
        match = pattern.fullmatch(row.get('name', ''))
        if match and row.get('digest') == image_digest:
            return match[1]
    return None


def check(db):
    installed = (db.components.find_one({'_id': 'host'}) or {}).get('installed', {})
    rows = []
    for name, tag in (('python', '3.13-slim'), ('gunicorn', '27'), ('mongo', '8.0')):
        current = installed.get(name, {})
        row = {'name': name, 'installed': current.get('version'), 'series': tag, 'state': 'unknown'}
        try:
            if name == 'gunicorn':
                versions = json_url('https://pypi.org/pypi/gunicorn/json')['releases']
                candidates = [v for v, files in versions.items() if re.fullmatch(r'27\.[0-9]+\.[0-9]+', v)
                              and any(not f.get('yanked') for f in files)]
                latest = max(candidates, key=lambda v: tuple(map(int, v.split('.'))))
                row['available'] = row['available_version'] = latest
                if current.get('version'):
                    row['state'] = 'available' if tuple(map(int, latest.split('.'))) > tuple(map(int, current['version'].split('.'))) else 'current'
            else:
                latest = registry_digest(name, tag)
                row['available'] = latest
                if current.get('digest'):
                    row['state'] = 'available' if latest != current['digest'] else 'current'
                if row['state'] == 'available':
                    try:
                        row['available_version'] = registry_version(name, tag, latest)
                    except (OSError, ValueError, KeyError, TypeError):
                        # An unavailable version label does not invalidate a verified image update.
                        row['available_version'] = None
        except Exception:
            # Never expose remote errors, authentication headers or command output.
            row['state'] = 'unknown'
        rows.append(row)
    db.components.update_one({'_id': 'host'}, {'$set': {'rows': rows, 'checked_at': time.time()}})
    return all(row['state'] != 'unknown' for row in rows)


def main():
    from app import database
    db = database()
    command = sys.argv[1]
    if command == 'heartbeat':
        heartbeat(db)
    elif command == 'claim':
        print(claim(db))
    elif command == 'recover':
        db.components.update_one({'_id': 'host', 'status': 'running'},
            {'$set': {'status': 'failed', 'result': 'interrupted', 'finished_at': time.time()}})
    elif command == 'inventory' and len(sys.argv) == 4:
        inventory(db, *sys.argv[2:])
    elif command == 'check':
        sys.exit(0 if check(db) else 1)
    elif command == 'finish' and sys.argv[2] in ('success', 'failed', 'deferred', 'release_changed'):
        db.components.update_one({'_id': 'host', 'status': 'running'},
            {'$set': {'status': sys.argv[2], 'result': sys.argv[2], 'finished_at': time.time()}})
    elif command == 'phase' and sys.argv[2] in ('preparing', 'downloading', 'building', 'restarting', 'verifying'):
        db.components.update_one({'_id': 'host', 'status': 'running'}, {'$set': {'phase': sys.argv[2]}})
    else:
        raise SystemExit('Unsupported host agent command')


if __name__ == '__main__':
    main()
