import secrets
import hmac
from flask import Blueprint, current_app, jsonify, render_template, request, session
from ..services.identity import current_user, allowed_dashboards, authorize, local_test_enabled, require_local_request, local_test_user
from ..services.orchestrator import run
from ..integrations.tableau import Tableau

bp = Blueprint('api', __name__)


def config():
    return current_app.config['HKELI']


@bp.before_request
def csrf():
    if local_test_enabled(config()):
        require_local_request()
    if request.method == 'POST' and not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), session.get('csrf', '!')):
        raise PermissionError('Invalid CSRF token. Reload the page.')


@bp.get('/')
def index():
    return render_template('index.html')


@bp.get('/api/session')
def bootstrap():
    session.setdefault('csrf', secrets.token_urlsafe(32))
    profiles = [{k: u[k] for k in ('id', 'name', 'country', 'line_of_business')} for u in config()['users']] if config()['app']['mode'] == 'demo' else []
    return jsonify(csrf=session['csrf'], mode=config()['app']['mode'], profiles=profiles, local_test=local_test_enabled(config()))


@bp.post('/api/login')
def login():
    if local_test_enabled(config()):
        require_local_request()
        local_test_user(config())
        session.clear()
        session.update(local_test_login=True, csrf=secrets.token_urlsafe(32))
        return jsonify(csrf=session['csrf'])
    if config()['app']['mode'] != 'demo':
        raise PermissionError('Mock login is disabled; use the approved SSO integration.')
    user_id = (request.get_json() or {}).get('user_id')
    if user_id not in {u['id'] for u in config()['users']}:
        raise PermissionError('Unknown demo profile.')
    session.clear()
    session.update(user_id=user_id, csrf=secrets.token_urlsafe(32))
    return jsonify(csrf=session['csrf'])


@bp.post('/api/logout')
def logout():
    session.clear()
    return jsonify(status='signed_out')


@bp.get('/api/dashboards')
def dashboards():
    user = current_user(config())
    return jsonify(user={k: user[k] for k in ('id', 'country', 'line_of_business')}, dashboards=[
        {'key': d['key'], 'label': d['label']} for d in allowed_dashboards(config(), user)])


@bp.post('/api/chat')
def chat():
    user = current_user(config())
    data = request.get_json() or {}
    question, selected = data.get('question'), data.get('dashboards')
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
        raise ValueError('Question must contain 1–2000 characters.')
    if not isinstance(selected, list) or len(selected) > 10 or any(not isinstance(v, str) for v in selected):
        raise ValueError('Provide selected dashboard keys.')
    authorize(config(), user, selected)
    settings = config()
    try:
        def execute():
            result = run(settings, user, selected, question)
            result['selected_dashboards'] = selected
            return result
        key = current_app.extensions['jobs'].submit(user['id'], execute)
    except OverflowError as error:
        return jsonify(error=str(error)), 429
    return jsonify(job_id=key, status='pending'), 202


@bp.get('/api/jobs/<key>')
def job(key):
    user = current_user(config())
    try:
        result = current_app.extensions['jobs'].get(user['id'], key)
        if result.get('answer'):
            authorize(config(), user, result['answer']['selected_dashboards'])
        if result.get('answer', {}).get('view_id'):
            # Revalidate current entitlements before releasing an embed authentication token.
            answer = result['answer']
            dashboard_key = answer['dashboard_key']
            authorize(config(), user, [dashboard_key])
        return jsonify(result)
    except KeyError:
        return jsonify(error='Job not found or expired.'), 404


@bp.post('/api/embed-token')
def embed_token():
    user = current_user(config())
    data = request.get_json() or {}
    selected = data.get('dashboards', [])
    if not isinstance(selected, list) or any(not isinstance(v, str) for v in selected):
        raise ValueError('Invalid dashboards.')
    dashboards = authorize(config(), user, selected)
    if config()['app']['mode'] != 'live':
        raise ValueError('Synthetic demo does not issue Tableau tokens.')
    client = Tableau(config(), user)
    if data.get('view_id') not in {v['id'] for v in client.catalog(dashboards)}:
        raise PermissionError('The view is outside your selected dashboards.')
    return jsonify(token=client.jwt(['tableau:views:embed']), expires_in=300)
