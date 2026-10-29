from flask import request, session
from ..config import plugin
import os
import ipaddress


def local_test_enabled(config):
    return config['app']['mode'] == 'live' and config.get('identity', {}).get('local_test_enabled') is True


def require_local_request():
    from urllib.parse import urlsplit
    try:
        local_peer = ipaddress.ip_address(request.remote_addr or '').is_loopback
    except ValueError:
        local_peer = False
    host = urlsplit(request.host_url).hostname
    if not local_peer or host not in ('localhost', '127.0.0.1', '::1') or any(
        h in request.headers for h in ('Forwarded', 'X-Forwarded-For', 'X-Forwarded-Host')
    ):
        raise PermissionError('Single-user test login permits direct localhost access only; proxies and tunnels are not supported.')


def local_test_user(config):
    settings = config['identity']
    username = os.getenv(settings.get('local_test_tableau_username_env', 'TABLEAU_CONNECTED_USERNAME'), '').strip()
    country = settings.get('local_test_country', '').strip()
    business = settings.get('local_test_line_of_business', '').strip()
    if not username or not country or not business:
        raise ValueError('Configure the local test Tableau username environment variable, country and line of business.')
    return {'id': 'local-single-user', 'country': country, 'line_of_business': business, 'tableau_username': username}


def current_user(config):
    if config['app']['mode'] == 'live':
        if local_test_enabled(config):
            require_local_request()
            if session.get('local_test_login') is not True:
                raise PermissionError('Use the single-user local test login first.')
            return local_test_user(config)
        resolver = config['identity']['resolver']
        if not resolver:
            raise PermissionError('Production identity resolver is not configured.')
        # Adapter must verify SSO signature, issuer, audience, expiry and trusted groups.
        user = plugin(resolver)(request)
    else:
        user = next((u for u in config['users'] if u['id'] == session.get('user_id')), None)
    if not user or not all(user.get(k) for k in ('id', 'country', 'line_of_business')):
        raise PermissionError('Please sign in.')
    return dict(user)


def allowed_dashboards(config, user):
    return [d for d in config['dashboards'] if user['country'] in d['countries']
            and user['line_of_business'] in d['lines_of_business']]


def authorize(config, user, selected):
    allowed = {d['key']: d for d in allowed_dashboards(config, user)}
    if not selected or len(selected) != len(set(selected)):
        raise ValueError('Select one or more dashboards.')
    if any(key not in allowed for key in selected):
        raise PermissionError('Your country and line of business do not permit the selected dashboard.')
    return [allowed[key] for key in selected]
