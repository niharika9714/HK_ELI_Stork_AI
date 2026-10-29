import copy
import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import ROOT, load_config
from app.integrations import stork
from app.models import Plan
from app.services.analysis import Analysis
from app.services.knowledge import Knowledge
from app.services.orchestrator import run


class KnowledgeLargeTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / 'config.example.toml')

    def catalog(self):
        pack = json.loads((ROOT.parent / 'knowledge/hkeli-demo/catalog.json').read_text(encoding='utf-8'))
        return [{'id': r['record_id'], 'name': r['view_name'], 'workbook_content_url': r['workbook_content_url'],
                 'dashboard': 'hk-sales', 'url': 'https://tableau.example/views/Book/' + r['record_id']} for r in pack['views']]

    def source_response(self, question, full=True, quote=None):
        return json.dumps({'action': 'native', 'view_id': 'view-product-mix', 'dashboard': 'hk-sales',
            'request_understanding': {'measures': ['notional'], 'dimensions': ['product types'], 'conditions': []},
            'requirements': [{'quote': quote or question}],
            'selection_assessment': {'view_id': 'view-product-mix', 'dashboard': 'hk-sales',
                'relevance_reason': 'Product notional distribution rather than a scalar P&L KPI.', 'full_match': full,
                'missing_requirements': [] if full else ['Product dimension']}})

    def call_model(self, question, response, candidates, knowledge):
        def adapter(settings, prompt):
            self.prompt = json.loads(prompt)
            return response
        env = {'One_Bank_ID': 'synthetic-user', 'One_BANK_PASSWORD': 'synthetic-password', 'SSL_CERT_FILE': 'synthetic-ca-path'}
        with patch.dict(os.environ, env), patch('app.integrations.stork.plugin', return_value=adapter):
            return stork.plan(self.config, question, candidates, knowledge=knowledge)

    def test_all_scoped_views_and_complete_documents_reach_existing_model(self):
        catalog = self.catalog()
        knowledge = Knowledge(self.config, self.config['dashboards'], catalog)
        question = 'Show how the notional is distributed across product types.'
        result = self.call_model(question, self.source_response(question), knowledge.candidates(catalog), knowledge.context())
        self.assertEqual(result.view_id, 'view-product-mix')
        self.assertEqual(len(self.prompt['catalog']), len(catalog))
        documents = self.prompt['business_knowledge_reference_only']['business_documents']
        self.assertTrue(any(d['reference'] == 'views/view-product-mix.md' for d in documents))
        self.assertTrue(any('knockout' in d['content'].lower() for d in documents))
        self.assertNotIn('synthetic-password', json.dumps(self.prompt))
        self.assertEqual(self.prompt['original_user_question'], question)
        self.assertIn('sole semantic source selector', self.prompt['instructions'])

    def test_copied_catalog_requirement_is_rejected(self):
        question = 'Show notional by product types.'
        with self.assertRaisesRegex(ValueError, 'original user question'):
            self.call_model(question, self.source_response(question, quote='Show the complete synthetic ELI dashboard'), self.catalog(), {})

    def test_model_declared_incomplete_match_is_rejected(self):
        question = 'Show notional by product types.'
        with self.assertRaisesRegex(ValueError, 'incomplete native match'):
            self.call_model(question, self.source_response(question, full=False), self.catalog(), {})

    def test_out_of_scope_source_is_rejected(self):
        question = 'Show notional by product types.'
        response = json.loads(self.source_response(question)); response['dashboard'] = 'not-selected'
        with self.assertRaisesRegex(ValueError, 'outside selected authorized'):
            self.call_model(question, json.dumps(response), self.catalog(), {})

    def test_unknown_paraphrase_is_sent_to_llm_without_phrase_gate(self):
        question = 'Explain the composition of our book across instrument families.'
        result = self.call_model(question, self.source_response(question), self.catalog(), {})
        self.assertEqual(result.view_id, 'view-product-mix')

    def test_unselected_view_cards_not_loaded(self):
        knowledge = Knowledge(self.config, self.config['dashboards'], [self.catalog()[0]])
        cards = [d for d in knowledge.documents if d['reference'].startswith('views/')]
        self.assertEqual(len(cards), 1)

    def test_knowledge_and_prompt_budgets_fail_without_partial_context(self):
        self.config['knowledge']['max_characters'] = 10
        with self.assertRaisesRegex(ValueError, 'capacity|budget'):
            Knowledge(self.config, self.config['dashboards'], self.catalog())
        self.config['knowledge']['max_prompt_characters'] = 10
        with self.assertRaisesRegex(ValueError, 'No candidates were silently omitted'):
            self.call_model('Show notional', self.source_response('Show notional'), self.catalog(), {})

    def test_sg_access_denied_before_knowledge_or_model_call(self):
        with patch('app.services.orchestrator.Knowledge', side_effect=AssertionError('No KB access')), patch('app.services.orchestrator.stork.plan', side_effect=AssertionError('No model')):
            with self.assertRaises(PermissionError):
                run(self.config, self.config['users'][1], ['hk-sales'], 'Show notional')

    def test_exact_100000_rows_last_outlier_and_generic_snapshot_contract(self):
        contract = {'verified_export': True, 'columns': {'Bucket': {'type': 'text'},
                    'Quantity': {'type': 'number', 'unit': 'number', 'additive': True},
                    'Cut': {'type': 'date', 'date_role': 'snapshot'}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.csv'
            with path.open('w', newline='') as stream:
                writer = csv.writer(stream); writer.writerow(['Bucket', 'Quantity', 'Cut'])
                for i in range(100000):
                    writer.writerow(['A' if i % 2 else 'B', 1000000 if i == 99999 else 1, '2026-01-01'])
            analysis = Analysis(path, self.config, contract)
            try:
                result = analysis.execute(Plan(action='analyze', measure='Quantity', aggregation='sum'))
                self.assertEqual(result['input_rows'], 100000)
                self.assertEqual(result['rows'][0]['value'], '1099999.00000000')
                self.assertLess(len(json.dumps(result)), 1000)
                analysis.db.execute("INSERT INTO data VALUES ('C', 1, DATE '2026-01-02')")
                with self.assertRaisesRegex(ValueError, 'snapshot/unknown dates'):
                    analysis.execute(Plan(action='analyze', measure='Quantity', aggregation='sum'))
                filtered = analysis.execute(Plan(action='analyze', measure='Quantity', aggregation='sum',
                    filters=[{'column': 'Cut', 'operator': 'eq', 'value': '2026-01-01'}]))
                self.assertEqual(filtered['rows'][0]['value'], '1099999.00000000')
            finally:
                analysis.close()

    def test_unverified_contract_never_grants_additivity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.csv'; path.write_text('Quantity\n1\n2\n')
            analysis = Analysis(path, self.config, {'verified_export': False, 'columns': {'Quantity': {'type': 'number', 'additive': True}}})
            try:
                with self.assertRaisesRegex(ValueError, 'Additivity'):
                    analysis.execute(Plan(action='analyze', measure='Quantity', aggregation='sum'))
            finally:
                analysis.close()


if __name__ == '__main__':
    unittest.main()
