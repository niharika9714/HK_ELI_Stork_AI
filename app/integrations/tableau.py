import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from urllib.parse import quote, urlsplit
import requests
from .ca_transport import tableau_transport


class Tableau:
    def __init__(self, config, user):
        self.config = config
        self.settings = config['tableau']
        self.user = user
        self.server = self.settings['server'].rstrip('/')
        url = urlsplit(self.server)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.path or url.query or url.fragment:
            raise ValueError('Tableau server must be a trusted HTTPS origin.')
        if not re.fullmatch(r'\d+\.\d+', self.settings['api_version']):
            raise ValueError('Invalid Tableau API version.')
        self.base = self.server + '/api/' + self.settings['api_version']
        self.ca_bundle = os.getenv(self.settings['ca_bundle_env'], '')
        self.verify = True

    def jwt(self, scopes):
        secret = os.getenv(self.settings['secret_value_env'], '')
        username = self.user.get('tableau_username')
        if not secret or not username or not self.settings['client_id'] or not self.settings['secret_id']:
            raise ValueError('Connected App configuration or verified Tableau identity is missing.')
        def enc(value):
            return base64.urlsafe_b64encode(json.dumps(value, separators=(',', ':')).encode()).decode().rstrip('=')
        token = enc({'alg': 'HS256', 'typ': 'JWT', 'kid': self.settings['secret_id'], 'iss': self.settings['client_id']}) + '.' + enc({
            'iss': self.settings['client_id'], 'sub': username, 'aud': 'tableau',
            'exp': int(time.time()) + 300, 'jti': str(uuid.uuid4()), 'scp': scopes})
        return token + '.' + base64.urlsafe_b64encode(hmac.new(secret.encode(), token.encode(), hashlib.sha256).digest()).decode().rstrip('=')

    @contextmanager
    def session(self):
        with tableau_transport(self.ca_bundle) as (transport, trust), requests.Session() as fallback:
            client = transport if isinstance(transport, requests.Session) else fallback
            self.verify = trust['verify']
            token = ''
            try:
                response = client.post(self.base + '/auth/signin', json={'credentials': {
                    'jwt': self.jwt(['tableau:content:read', 'tableau:views:download']),
                    'site': {'contentUrl': self.settings['site'] or ''}}},
                    headers={'Accept': 'application/json'}, verify=self.verify, timeout=(5, 30), allow_redirects=False)
                self.check(response)
                credentials = response.json()['credentials']
                token = credentials['token']
                client.headers.update({'X-Tableau-Auth': token, 'Accept': 'application/json'})
                yield client, self.base + '/sites/' + quote(credentials['site']['id'], safe='')
            finally:
                if token:
                    try:
                        client.post(self.base + '/auth/signout', headers={'X-Tableau-Auth': token},
                                    verify=self.verify, timeout=(5, 8), allow_redirects=False)
                    except requests.RequestException:
                        pass

    @staticmethod
    def check(response):
        if response.status_code in (401, 403):
            raise PermissionError('Tableau rejected this user or denied access to this resource.')
        if response.status_code != 200:
            raise ValueError('Tableau integration HTTP ' + str(response.status_code))

    def pages(self, client, url, envelope, member):
        output = []
        for page in range(1, 101):
            response = client.get(url, params={'pageSize': 100, 'pageNumber': page},
                                  verify=self.verify, timeout=(5, 30), allow_redirects=False)
            self.check(response)
            data = response.json()
            values = data.get(envelope, {}).get(member, [])
            output.extend(values)
            if 'pagination' not in data or page * 100 >= int(data['pagination']['totalAvailable']):
                return output
        raise ValueError('Catalog pagination exceeded configured bound; no partial catalog used.')

    def catalog(self, dashboards):
        result = []
        with self.session() as (client, root):
            workbooks = self.pages(client, root + '/workbooks', 'workbooks', 'workbook')
            for dashboard in dashboards:
                matches = [w for w in workbooks if w['name'] == dashboard['workbook_name']]
                if len(matches) != 1:
                    raise ValueError('Configured workbook is missing or ambiguous for this user.')
                views = self.pages(client, root + '/workbooks/' + quote(matches[0]['id'], safe='') + '/views', 'views', 'view')
                permitted = set(dashboard['worksheet_names']) | {dashboard['dashboard_view_name']}
                for view in views:
                    if view['name'] not in permitted:
                        continue
                    route = view.get('contentUrl', '').replace('/sheets/', '/')
                    if not route or '..' in route or not re.fullmatch(r'[\w /.-]+', route):
                        raise ValueError('Invalid discovered Tableau view route.')
                    prefix = '/t/' + quote(self.settings['site'], safe='') if self.settings['site'] else ''
                    result.append({'id': view['id'], 'name': view['name'], 'dashboard': dashboard['key'],
                                   'url': self.server + prefix + '/views/' + quote(route, safe='/')})
        return result

    def export(self, view, target):
        with self.session() as (client, root):
            with client.get(root + '/views/' + quote(view['id'], safe='') + '/data',
                            headers={'Accept': '*/*'}, stream=True, verify=self.verify,
                            timeout=(5, 30), allow_redirects=False) as response:
                self.check(response)
                size = 0
                with open(target, 'wb') as output:
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        if size > self.config['app']['max_export_bytes']:
                            raise ValueError('Authorized export exceeds the configured byte budget; no sampling performed.')
                        output.write(chunk)
