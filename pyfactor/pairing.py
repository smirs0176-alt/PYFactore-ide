from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus

from flask import Blueprint, Flask, current_app, jsonify, request

bp = Blueprint('pairing', __name__)

# --- real Google OAuth helpers -------------------------------------------------

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'  # noqa: S105
GOOGLE_USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'


def _http_json(url, *, method='GET', data=None, headers=None):
    payload = None
    if data is not None:
        payload = urllib.parse.urlencode(data).encode('utf-8')
    req = urllib.request.Request(url, data=payload, method=method)  # noqa: S310
    if headers:
        for key, value in headers.items():
            req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310
            body = response.read().decode('utf-8') or '{}'
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode('utf-8') or '{}'
            return json.loads(body)
        except Exception:
            return {'error': f'http_{exc.code}'}
    except urllib.error.URLError as exc:
        raise RuntimeError(f'Нет связи с сервером Google: {exc.reason}') from exc


def build_google_auth_url(client_id: str, redirect_uri: str, state: str | None = None, offline: bool = False) -> str:
    if not client_id:
        raise ValueError('client_id is required')
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid email profile',
        'prompt': 'select_account',
    }
    if offline:                                   # refresh-токен нужен не всем: по умолчанию не просим
        params['access_type'] = 'offline'
    if state:
        params['state'] = state
    return GOOGLE_AUTH_URL + '?' + urllib.parse.urlencode(params)


def exchange_google_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    if not client_id or not client_secret or not code or not redirect_uri:
        raise ValueError('client_id, client_secret, code and redirect_uri are required')
    token_data = _http_json(
        GOOGLE_TOKEN_URL,
        method='POST',
        data={
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        },
        headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'},
    )
    if 'access_token' not in token_data:
        raise RuntimeError(token_data.get('error_description') or token_data.get('error') or 'Google не выдал токен')
    userinfo = _http_json(
        GOOGLE_USERINFO_URL,
        headers={'Authorization': 'Bearer ' + token_data['access_token'], 'Accept': 'application/json'},
    )
    if 'email' not in userinfo:
        raise RuntimeError('Google userinfo не вернул email')
    if userinfo.get('email_verified', True) is False:
        raise RuntimeError('Почта Google не подтверждена')
    return {
        'provider': 'Google',
        'email': userinfo.get('email', ''),
        'name': userinfo.get('name') or userinfo.get('email', ''),
        'picture': userinfo.get('picture', ''),
        'token': token_data['access_token'],
        'refresh_token': token_data.get('refresh_token', ''),
    }


# --- pairing prototype -----------------------------------------------------------
# Прототип, к сайту и IDE не подключён. Что исправлено после аудита:
#  * владелец пары берётся не из тела запроса, а из заголовка Authorization: Bearer через проверяющую функцию PAIR_AUTH
#    (create_app(auth=...)); без неё /api/pair/create отвечает 503, а не выдаёт коды от чужого имени;
#  * код гасится атомарно (блокировка), выданный токен хранится как sha256 и проверяется через owner_of();
#  * тело запроса — только JSON-объект (раньше force=True и 500 на списке), число записей и частота проверок ограничены;
#  * Google-маршруты берут ключи только из окружения сервера, state выдаёт и проверяет сервер, токены Google клиенту не отдаются.
# Остаётся: хранилище в памяти одного процесса (несколько воркеров его не делят), TLS и CORS — на стороне сервера, где это подключат.

LOCK = threading.RLock()
PAIR_STORE: dict = {}
TOKENS: dict = {}
OAUTH_STATES: dict = {}
HITS: dict = {}


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(os.getenv(name, str(default)))))
    except ValueError:
        return default


PAIR_TTL = _env_int('PAIR_TTL', 300, 30, 3600)
TOKEN_TTL = _env_int('PAIR_TOKEN_TTL', 30 * 24 * 3600, 60, 365 * 24 * 3600)
STATE_TTL = 600
MAX_ENTRIES = 10_000
CHECKS_PER_MINUTE = 20


def create_app(auth=None) -> Flask:
    """auth(token) -> email | None. Без auth создание кодов выключено."""
    app = Flask(__name__)
    app.config['PAIR_AUTH'] = auth
    app.config['MAX_CONTENT_LENGTH'] = 64 * 1024
    app.register_blueprint(bp)
    return app


def _json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _bad(error='bad_request', status=HTTPStatus.BAD_REQUEST):
    return jsonify({'error': error}), status


def _cleanup(now=None):
    now = now or time.time()
    for store, key in ((PAIR_STORE, 'expires'), (TOKENS, 'expires'), (OAUTH_STATES, 'expires')):
        for k, v in list(store.items()):
            if v[key] < now:
                store.pop(k, None)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def owner_of(token) -> str | None:
    """Кому выдан токен пары (None — неизвестный или просроченный)."""
    if not token:
        return None
    with LOCK:
        e = TOKENS.get(_hash(str(token)))
        return e['owner'] if e and e['expires'] >= time.time() else None


def _authed_user():
    verify = current_app.config.get('PAIR_AUTH')
    if verify is None:
        return None, True
    h = request.headers.get('Authorization', '')
    if not h.lower().startswith('bearer '):
        return None, False
    try:
        return verify(h[7:].strip()) or None, False
    except Exception:
        return None, False


def _rate_ok(key: str) -> bool:
    now = time.time()
    with LOCK:
        hits = [t for t in HITS.get(key, []) if now - t < 60]
        if len(hits) >= CHECKS_PER_MINUTE:
            HITS[key] = hits
            return False
        hits.append(now)
        HITS[key] = hits
        if len(HITS) > MAX_ENTRIES:
            HITS.clear()
        return True


def _google_config():
    return (os.getenv('GOOGLE_CLIENT_ID'), os.getenv('GOOGLE_CLIENT_SECRET'),
            os.getenv('GOOGLE_REDIRECT_URI', 'http://127.0.0.1:5000/api/oauth/google/callback'))


@bp.route('/api/oauth/google/start', methods=['POST'])
def google_start():
    client_id, _secret, redirect_uri = _google_config()
    if not client_id:
        return _bad('client_id_missing')
    state = secrets.token_urlsafe(24)
    with LOCK:
        _cleanup()
        if len(OAUTH_STATES) >= MAX_ENTRIES:
            return _bad('busy', HTTPStatus.SERVICE_UNAVAILABLE)
        OAUTH_STATES[state] = {'expires': time.time() + STATE_TTL}
    return jsonify({'auth_url': build_google_auth_url(client_id, redirect_uri, state), 'state': state}), HTTPStatus.OK


@bp.route('/api/oauth/google/callback', methods=['POST'])
def google_callback():
    data = _json_body()
    if data is None:
        return _bad()
    code, state = data.get('code'), data.get('state')
    if not isinstance(code, str) or not code:
        return _bad('code_missing')
    with LOCK:                                    # state одноразовый и выдан этим сервером
        _cleanup()
        ok = isinstance(state, str) and OAUTH_STATES.pop(state, None) is not None
    if not ok:
        return _bad('bad_state')
    client_id, client_secret, redirect_uri = _google_config()
    if not client_id or not client_secret:
        return _bad('google_credentials_missing')
    try:
        user = exchange_google_code(client_id, client_secret, code, redirect_uri)
    except (RuntimeError, ValueError) as exc:
        return _bad(str(exc))
    user.pop('token', None)                       # токены Google остаются на сервере и клиенту не нужны
    user.pop('refresh_token', None)
    return jsonify({'user': user}), HTTPStatus.OK


@bp.route('/api/pair/create', methods=['POST'])
def create_pair():
    if _json_body() is None:
        return _bad()
    owner, not_configured = _authed_user()
    if not_configured:
        return _bad('auth_not_configured', HTTPStatus.SERVICE_UNAVAILABLE)
    if not owner:
        return _bad('unauthorized', HTTPStatus.UNAUTHORIZED)
    code = secrets.token_urlsafe(8)
    with LOCK:
        _cleanup()
        if len(PAIR_STORE) >= MAX_ENTRIES:
            return _bad('busy', HTTPStatus.SERVICE_UNAVAILABLE)
        PAIR_STORE[code] = {'owner': owner, 'expires': time.time() + PAIR_TTL, 'used': False}
    current_app.logger.info('pair create owner=%r', owner)
    return jsonify({'code': code, 'ttl': PAIR_TTL}), HTTPStatus.CREATED


@bp.route('/api/pair/check', methods=['POST'])
def check_pair():
    data = _json_body()
    if data is None:
        return _bad()
    if not _rate_ok(request.remote_addr or '?'):
        return _bad('too_many_requests', HTTPStatus.TOO_MANY_REQUESTS)
    code = data.get('code')
    token = secrets.token_urlsafe(24)
    with LOCK:                                    # проверка и «использован» — одним действием
        _cleanup()
        entry = PAIR_STORE.get(code) if isinstance(code, str) else None
        if entry is None:
            return _bad('invalid_or_expired')
        if entry['used']:
            return _bad('already_used')
        entry['used'] = True
        TOKENS[_hash(token)] = {'owner': entry['owner'], 'expires': time.time() + TOKEN_TTL}
        owner = entry['owner']
    current_app.logger.info('pair used owner=%r', owner)
    return jsonify({'token': token, 'user': owner}), HTTPStatus.OK
