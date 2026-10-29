import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.config import load_config


class LocalIdentityTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'HKELI_SESSION_SECRET': 'test-only-session-secret', 'TABLEAU_CONNECTED_USERNAME': 'test@example.invalid'})
        self.env.start()
        self.config = load_config(Path(__file__).resolve().parents[1] / 'config.example.toml')
        self.config['app']['mode'] = 'live'
        self.config['identity'].update(local_test_enabled=True, local_test_country='HK', local_test_line_of_business='sales')
        self.app = create_app(self.config)
        self.client = self.app.test_client()

    def tearDown(self):
        self.app.extensions['jobs'].pool.shutdown(wait=True)
        self.env.stop()

    def test_login_requires_csrf_and_uses_server_identity(self):
        csrf = self.client.get('/api/session').json['csrf']
        self.assertEqual(self.client.get('/api/dashboards').status_code, 403)
        self.assertEqual(self.client.post('/api/login', json={}).status_code, 403)
        response = self.client.post('/api/login', json={'tableau_username': 'attacker', 'country': 'SG'}, headers={'X-CSRF-Token': csrf})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/api/dashboards').json['user']['country'], 'HK')
        with self.app.test_request_context('/', environ_base={'REMOTE_ADDR': '127.0.0.1'}):
            from app.services.identity import local_test_user
            self.assertEqual(local_test_user(self.config)['tableau_username'], 'test@example.invalid')
        self.client.post('/api/logout', json={}, headers={'X-CSRF-Token': response.json['csrf']})
        self.assertEqual(self.client.get('/api/dashboards').status_code, 403)

    def test_remote_host_and_proxy_blocked(self):
        self.assertEqual(self.client.get('/api/session', environ_base={'REMOTE_ADDR': '192.0.2.1'}).status_code, 403)
        self.assertEqual(self.client.get('/api/session', headers={'Host': 'external.example'}).status_code, 403)
        self.assertEqual(self.client.get('/api/session', headers={'X-Forwarded-For': '127.0.0.1'}).status_code, 403)

    def test_disabled_preserves_corporate_resolver_requirement(self):
        self.config['identity']['local_test_enabled'] = False
        self.assertFalse(self.client.get('/api/session').json['local_test'])
        self.assertEqual(self.client.get('/api/dashboards').status_code, 403)

    def test_no_identity_without_configuration(self):
        csrf = self.client.get('/api/session').json['csrf']
        with patch.dict(os.environ, {'TABLEAU_CONNECTED_USERNAME': ''}):
            self.assertEqual(self.client.post('/api/login', json={}, headers={'X-CSRF-Token': csrf}).status_code, 400)
