import copy
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.config import load_config
from app.services.demo import export
from app.services.analysis import Analysis
from app.models import Plan


class AppTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(Path(__file__).resolve().parents[1] / 'config.example.toml')
        self.app = create_app(copy.deepcopy(self.config))
        self.client = self.app.test_client()
        self.csrf = self.client.get('/api/session').json['csrf']

    def tearDown(self):
        self.app.extensions['jobs'].pool.shutdown(wait=True)

    def post(self, path, data):
        return self.client.post('/api/' + path, json=data, headers={'X-CSRF-Token': self.csrf})

    def login(self, identity):
        self.csrf = self.post('login', {'user_id': identity}).json['csrf']

    def answer(self, question):
        response = self.post('chat', {'question': question, 'dashboards': ['hk-sales']})
        self.assertEqual(response.status_code, 202)
        key = response.json['job_id']
        for _ in range(200):
            result = self.client.get('/api/jobs/' + key).json
            if result['status'] != 'pending':
                return result
            time.sleep(.01)
        self.fail('Job did not complete')

    def test_sg_denied_before_retrieval(self):
        self.login('sg-sales-user')
        self.assertEqual(self.client.get('/api/dashboards').json['dashboards'], [])
        self.assertEqual(self.post('chat', {'question': 'show holdings', 'dashboards': ['hk-sales']}).status_code, 403)

    def test_hk_scenarios(self):
        self.login('hk-sales-user')
        for question in ['Show client holdings', 'Filter active holdings', 'Aggregate sub-product to product',
                         'Notional by year', 'Pie chart by product', 'Compare product and sector', 'Total notional']:
            with self.subTest(question=question):
                answer = self.answer(question)
                self.assertEqual(answer['status'], 'completed', answer)
                self.assertTrue(answer['answer']['citations'])

    def test_missing_metric_is_gap_not_denial(self):
        self.login('hk-sales-user')
        answer = self.answer('Show profit')['answer']
        self.assertEqual(answer['status'], 'clarification')

    def test_job_isolation(self):
        self.login('hk-sales-user')
        key = self.post('chat', {'question': 'Show holdings', 'dashboards': ['hk-sales']}).json['job_id']
        self.login('sg-sales-user')
        self.assertEqual(self.client.get('/api/jobs/' + key).status_code, 404)

    def test_csrf_and_live_mock_login(self):
        self.assertEqual(self.client.post('/api/login', json={'user_id': 'hk-sales-user'}).status_code, 403)
        self.app.config['HKELI']['app']['mode'] = 'live'
        self.assertEqual(self.post('login', {'user_id': 'hk-sales-user'}).status_code, 403)

    def test_full_100000_row_aggregation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.csv'
            export(path, 100000)
            analysis = Analysis(path, self.config, self.config['dashboards'][0])
            try:
                result = analysis.execute(Plan(action='analyze', measure='Notional HKD', aggregation='sum'))
                expected = sum((i % 7 + 1) * 1000 for i in range(100000))
                self.assertEqual(result['input_rows'], 100000)
                self.assertEqual(float(result['rows'][0]['value']), expected)
                with self.assertRaises(ValueError):
                    analysis.execute(Plan(action='analyze', dimensions=['Missing'], chart='bar'))
            finally:
                analysis.close()

    def test_optional_summary_failure_preserves_original(self):
        self.login('hk-sales-user')
        with patch('app.services.orchestrator.analytical_result', side_effect=ValueError('Synthetic export failure')):
            answer = self.answer('Show holdings and summarize it')['answer']
            self.assertEqual(answer['status'], 'demo_native')
            self.assertIn('analysis_error', answer)
            self.assertTrue(answer['citations'])

    def test_private_vertex_contract(self):
        import types
        import asyncio
        from app.integrations.vertex_adapter import generate
        calls = []
        async def content(**kwargs):
            calls.append(kwargs)
            return types.SimpleNamespace(text='{"action":"clarify"}')
        client = types.SimpleNamespace(aio=types.SimpleNamespace(models=types.SimpleNamespace(generate_content=content)))
        package = types.ModuleType('ada_genai')
        module = types.ModuleType('ada_genai.google_genai')
        module.VertexClient = lambda: client
        with patch.dict(sys.modules, {'ada_genai': package, 'ada_genai.google_genai': module}):
            result = generate({'model': 'test-private-model', 'timeout_seconds': 1}, 'safe prompt')
        self.assertEqual(calls, [{'model': 'test-private-model', 'content': 'safe prompt'}])
        self.assertIn('clarify', result)

    def test_invalid_model_source_is_not_executed(self):
        from app.services.orchestrator import run
        with patch('app.services.demo.plan', return_value=Plan(action='native', view_id='unauthorized-view')):
            with self.assertRaises(ValueError):
                run(self.config, self.config['users'][0], ['hk-sales'], 'show view')

    def test_native_filter_not_silently_ignored(self):
        from app.models import Condition
        from app.services.orchestrator import run
        decision = Plan(action='native', view_id='holdings', filters=[Condition(column='Country', operator='eq', value='SG')])
        with patch('app.services.demo.plan', return_value=decision):
            with self.assertRaises(ValueError):
                run(self.config, self.config['users'][0], ['hk-sales'], 'show filtered view')


if __name__ == '__main__':
    unittest.main()
