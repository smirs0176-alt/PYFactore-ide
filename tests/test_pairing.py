import threading
import time
from urllib.parse import parse_qs, urlparse

import pytest

from pyfactor import pairing
from pyfactor.pairing import build_google_auth_url, exchange_google_code

USERS = {"tok-alice": "alice@example.com", "tok-bob": "bob@example.com"}


@pytest.fixture
def client():
    for st in (pairing.PAIR_STORE, pairing.TOKENS, pairing.OAUTH_STATES, pairing.HITS):
        st.clear()
    app = pairing.create_app(auth=USERS.get)
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def H(tok):
    return {'Authorization': 'Bearer ' + tok}


def test_pairing_flow(client):
    r1 = client.post('/api/pair/create', json={}, headers=H('tok-alice'))
    assert r1.status_code == 201, r1.get_data(as_text=True)
    payload = r1.get_json()
    code = payload['code']
    assert code and payload['ttl'] > 0

    r2 = client.post('/api/pair/check', json={'code': code})
    assert r2.status_code == 200, r2.get_data(as_text=True)
    pair = r2.get_json()
    assert pair['user'] == 'alice@example.com' and pair['token']
    assert pairing.owner_of(pair['token']) == 'alice@example.com'      # токен можно проверить
    assert pairing.owner_of('forged') is None

    r3 = client.post('/api/pair/check', json={'code': code})
    assert r3.status_code == 400 and r3.get_json()['error'] == 'already_used'


def test_cannot_create_code_for_someone_else(client):
    assert client.post('/api/pair/create', json={'user': 'victim@example.com'}).status_code == 401
    assert client.post('/api/pair/create', json={}, headers=H('wrong')).status_code == 401
    r = client.post('/api/pair/create', json={'user': 'victim@example.com'}, headers=H('tok-bob'))
    code = r.get_json()['code']
    assert client.post('/api/pair/check', json={'code': code}).get_json()['user'] == 'bob@example.com'   # поле user из тела игнорируется


def test_create_disabled_without_auth_verifier():
    app = pairing.create_app()
    with app.test_client() as c:
        assert c.post('/api/pair/create', json={'user': 'x@y.z'}).status_code == 503


class _SlowEntry(dict):
    """Растягивает окно между «прочитали used» и «записали used=True», чтобы гонка проявлялась всегда, а не раз в тысячу запусков."""

    def __getitem__(self, key):
        v = super().__getitem__(key)
        if key == 'used':
            time.sleep(0.05)
        return v


def test_code_redeems_once_under_concurrency(client, monkeypatch):
    code = client.post('/api/pair/create', json={}, headers=H('tok-alice')).get_json()['code']
    pairing.PAIR_STORE[code] = _SlowEntry(pairing.PAIR_STORE[code])
    monkeypatch.setattr(pairing, 'CHECKS_PER_MINUTE', 1000)
    results, gate = [], threading.Barrier(6)

    def go():
        with client.application.test_client() as c:
            gate.wait()
            results.append(c.post('/api/pair/check', json={'code': code}).status_code)
    ts = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(results) == [200] + [400] * 5


def test_non_object_and_wrong_types_do_not_crash(client):
    for path in ('/api/pair/check', '/api/pair/create', '/api/oauth/google/callback'):
        assert client.post(path, json=[1, 2]).status_code == 400
        assert client.post(path, data='not json', content_type='text/plain').status_code == 400
    assert client.post('/api/pair/check', json={'code': {'a': 1}}).status_code == 400


def test_check_is_rate_limited(client):
    codes = [client.post('/api/pair/check', json={'code': 'nope%d' % i}).status_code for i in range(pairing.CHECKS_PER_MINUTE + 3)]
    assert codes[-1] == 429 and codes[0] == 400


def test_store_is_bounded(client, monkeypatch):
    monkeypatch.setattr(pairing, 'MAX_ENTRIES', 3)
    st = [client.post('/api/pair/create', json={}, headers=H('tok-alice')).status_code for _ in range(5)]
    assert st == [201, 201, 201, 503, 503]


def test_expired_code_is_rejected(client, monkeypatch):
    code = client.post('/api/pair/create', json={}, headers=H('tok-alice')).get_json()['code']
    pairing.PAIR_STORE[code]['expires'] = 0
    assert client.post('/api/pair/check', json={'code': code}).get_json()['error'] == 'invalid_or_expired'


def test_google_routes_use_server_keys_and_verify_state(client, monkeypatch):
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'SERVER_ID')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'SERVER_SECRET')
    seen = {}

    def fake_exchange(cid, sec, code, redirect):
        seen.update(cid=cid, sec=sec, code=code)
        return {'provider': 'Google', 'email': 'g@x.io', 'name': 'G', 'token': 'GOOGLE-AT', 'refresh_token': 'GOOGLE-RT'}
    monkeypatch.setattr(pairing, 'exchange_google_code', fake_exchange)

    st = client.post('/api/oauth/google/start', json={'client_id': 'EVIL', 'redirect_uri': 'http://evil'}).get_json()
    assert 'SERVER_ID' in st['auth_url'] and 'evil' not in st['auth_url'].lower()

    # чужой или отсутствующий state — отказ
    assert client.post('/api/oauth/google/callback', json={'code': 'c', 'state': 'forged'}).get_json()['error'] == 'bad_state'
    assert client.post('/api/oauth/google/callback', json={'code': 'c'}).get_json()['error'] == 'bad_state'
    assert not seen

    r = client.post('/api/oauth/google/callback', json={'code': 'c', 'state': st['state'], 'client_secret': 'ATTACKER', 'client_id': 'EVIL'})
    assert r.status_code == 200 and seen == {'cid': 'SERVER_ID', 'sec': 'SERVER_SECRET', 'code': 'c'}
    body = r.get_data(as_text=True)
    assert 'GOOGLE-AT' not in body and 'GOOGLE-RT' not in body                # токены Google клиенту не отдаются
    assert client.post('/api/oauth/google/callback', json={'code': 'c', 'state': st['state']}).get_json()['error'] == 'bad_state'  # одноразовый


def test_unverified_google_email_rejected(monkeypatch):
    def fake(url, *, method='GET', data=None, headers=None):
        return {'access_token': 't'} if url.endswith('/token') else {'email': 'e@x.io', 'email_verified': False}
    monkeypatch.setattr('pyfactor.pairing._http_json', fake)
    with pytest.raises(RuntimeError):
        pairing.exchange_google_code('i', 's', 'c', 'http://127.0.0.1/cb')


def test_offline_access_not_requested_by_default():
    assert 'access_type' not in pairing.build_google_auth_url('i', 'http://x/cb', 's')
    assert 'access_type=offline' in pairing.build_google_auth_url('i', 'http://x/cb', 's', offline=True)


def test_google_auth_url_and_exchange(monkeypatch):
    auth_url = build_google_auth_url('CLIENT_ID', 'http://127.0.0.1:5000/callback', state='abc')
    parsed = urlparse(auth_url)
    qs = parse_qs(parsed.query)
    assert parsed.netloc == 'accounts.google.com'
    assert qs['client_id'] == ['CLIENT_ID']
    assert qs['state'] == ['abc']
    assert qs['response_type'] == ['code']

    def fake_http_json(url, *, method='GET', data=None, headers=None):
        if url.endswith('/token'):
            return {'access_token': 'tok', 'refresh_token': 'ref'}
        if url.endswith('/userinfo'):
            return {'email': 'user@example.com', 'name': 'User', 'picture': 'http://example.com/avatar.png'}
        raise AssertionError(f'unexpected url: {url}')

    monkeypatch.setattr('pyfactor.pairing._http_json', fake_http_json)
    payload = exchange_google_code('CLIENT_ID', 'SECRET', 'code-123', 'http://127.0.0.1:5000/callback')
    assert payload['email'] == 'user@example.com'
    assert payload['token'] == 'tok'
    assert payload['refresh_token'] == 'ref'
