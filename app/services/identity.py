from flask import request, session
from ..config import plugin


def current_user(config):
    if config['app']['mode'] == 'live':
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
