"""Explicit update authorization, persistent jobs and truthful update checks."""
import time
from unittest.mock import patch

import pytest
import components
import security
from test_app import db
from test_security import secured


def test_only_authenticated_confirmed_update_requests_can_be_queued(secured):
    server, client = secured
    components.heartbeat(server.db)
    assert client.call('/ui/components')[0] == 401
    assert client.call('/ui/components/update', {'confirmed':True})[0] == 401
    assert client.login()[0] == 200
    assert client.call('/ui/components/update', {})[0] == 400
    assert client.call('/ui/components/update', {'confirmed':False})[0] == 400
    assert client.call('/ui/components/update', {'confirmed':1})[0] == 400
    assert client.call('/ui/components/update', {'confirmed':True},headers={'X-Off-Proxy-Control':'bad'})[0] == 403
    assert server.db.components.find_one({'_id':'host'})['status'] == 'idle'
    assert client.call('/ui/components/update', {'confirmed':True})[1]['queued'] is True
    assert client.call('/ui/components/update', {'confirmed':True})[1]['queued'] is False
    assert components.claim(server.db) == 'update'
    assert components.claim(server.db) == ''


def test_queue_requires_live_host_and_defers_during_import(db):
    with pytest.raises(security.Denied): components.request(db,'update')
    components.heartbeat(db)
    db.scheduler.insert_one({'_id':'sync','phase':'running'})
    with pytest.raises(security.Denied) as error: components.request(db,'update')
    assert error.value.status == 409
    assert components.request(db,'check') is True


def test_heartbeats_never_schedule_updates_and_expired_requests_are_not_run(db):
    for _ in range(5): components.heartbeat(db)
    assert components.claim(db) == ''
    assert components.request(db,'update')
    db.components.update_one({'_id':'host'},{'$set':{'requested_at':time.time()-301}})
    assert components.claim(db) == ''
    assert components.snapshot(db)['result'] == 'expired'


def test_update_checks_compare_pinned_images_and_compatible_published_releases(db):
    components.heartbeat(db)
    db.components.update_one({'_id':'host'},{'$set':{'installed': {
        'python':{'version':'3.13.10','digest':'python@sha256:'+'a'*64},
        'mongo':{'version':'8.0.10','digest':'mongo@sha256:'+'b'*64},
        'gunicorn':{'version':'27.0.1'}}}})
    versions={'releases':{'27.0.1':[{}],'27.0.2':[{}],'27.0.3':[{'yanked':True}],'28.0.0':[{}],'27.1.0rc1':[{}]}}
    with patch.object(components,'registry_digest',side_effect=['python@sha256:'+'a'*64,'mongo@sha256:'+'c'*64]), patch.object(components,'json_url',return_value=versions), patch.object(components,'registry_version',return_value='8.0.11'):
        assert components.check(db)
    rows=components.snapshot(db)['rows']
    assert [r['state'] for r in rows] == ['current','available','available']
    assert rows[1]['available_version'] == '27.0.2'
    assert rows[2]['available_version'] == '8.0.11'
    assert components.claim(db) == ''


@pytest.mark.parametrize('repository, tag, matching_tag, version', [
    ('mongo', '8.0', '8.0.39', '8.0.39'),
    ('python', '3.13-slim', '3.13.19-slim', '3.13.19'),
])
def test_image_target_version_must_match_the_checked_digest(repository, tag, matching_tag, version):
    digest = 'sha256:' + 'a' * 64
    rows = {'results': [
        {'name': matching_tag, 'digest': 'sha256:' + 'b' * 64},
        {'name': tag, 'digest': digest},
    ]}
    with patch.object(components, 'json_url', return_value=rows):
        assert components.registry_version(repository, tag, repository+'@'+digest) is None
        rows['results'].append({'name': matching_tag, 'digest': digest})
        assert components.registry_version(repository, tag, repository+'@'+digest) == version


def test_unreachable_sources_and_missing_build_provenance_are_unknown(db):
    components.heartbeat(db)
    with patch.object(components,'registry_digest',side_effect=OSError('private details')), patch.object(components,'json_url',side_effect=OSError('secret')):
        assert not components.check(db)
    state=components.snapshot(db)
    assert all(r['state']=='unknown' for r in state['rows'])
    assert 'secret' not in repr(state) and 'private details' not in repr(state)


def test_component_snapshot_does_not_expose_private_state(db):
    db.components.insert_one({'_id':'host','password':'secret','host_path':'private','status':'idle'})
    assert 'secret' not in repr(components.snapshot(db))
    with pytest.raises(ValueError): components.request(db,'rm -rf /')


@pytest.mark.parametrize('url',['http://pypi.org/pypi/gunicorn/json','https://example.org/','file:///etc/passwd','https://pypi.org:444/'])
def test_update_checks_only_contact_fixed_https_sources(url):
    import urllib.request
    with pytest.raises(ValueError): components.open_https(urllib.request.Request(url))


def test_update_sources_may_not_redirect_credentials():
    with pytest.raises(ValueError): components.NoRedirect().redirect_request(None,None,302,None,None,'https://evil.invalid')


def test_current_components_require_explicit_reinstall_confirmation(secured):
    server, client=secured
    components.heartbeat(server.db)
    server.db.components.update_one({'_id':'host'},{'$set':{
        'rows':[{'name':name,'state':'current'} for name in ('python','gunicorn','mongo')]}})
    assert client.login()[0]==200
    result=client.call('/ui/components/update',{'confirmed':True})
    assert result[0]==409 and result[1]['error']=='components_already_current'
    assert server.db.components.find_one({'_id':'host'})['status']=='idle'
    for invalid in (False,1,'true',None):
        assert client.call('/ui/components/update',{'confirmed':True,'reinstall':invalid})[0]==400
    assert client.call('/ui/components/update',{'confirmed':True,'reinstall':True},
                       headers={'X-Off-Proxy-Control':'invalid'})[0]==403
    assert client.call('/ui/components/update',{'confirmed':True,'reinstall':True})[1]['queued'] is True
    assert client.call('/ui/components/update',{'confirmed':True,'reinstall':True})[1]['queued'] is False
    assert components.claim(server.db)=='update'
    assert components.claim(server.db)==''


@pytest.mark.parametrize('states',[
    ['current','current','unknown'],['current','available','current'],['current','current']])
def test_partial_or_unknown_checks_do_not_mean_everything_is_current(db,states):
    components.heartbeat(db)
    db.components.update_one({'_id':'host'},{'$set':{
        'rows':[{'name':name,'state':state} for name,state in zip(('python','gunicorn','mongo'),states)]}})
    assert components.request(db,'update')
