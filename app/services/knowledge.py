"""Load complete, scoped business knowledge; no Python intent matching or ranking."""
import json
from pathlib import Path
from ..config import ROOT


def _path(value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


class Knowledge:
    def __init__(self, config, dashboards, catalog, demo=False):
        self.config, self.records, self.documents, self.concepts = config, {}, [], []
        settings = config.get('knowledge', {})
        paths = {}
        for dashboard in dashboards:
            configured = settings.get('demo_pack') if demo else dashboard.get('knowledge_pack')
            if configured:
                paths[dashboard['key']] = _path(configured)
        total = 0
        concepts = {}
        for dashboard_key, directory in paths.items():
            source = directory / 'catalog.json'
            if not source.is_file():
                raise ValueError('Configured knowledge catalog is missing; no definitions were invented.')
            if source.stat().st_size > settings.get('max_characters', 80000) * 4:
                raise ValueError('Knowledge catalog exceeds configured capacity.')
            raw = source.read_text(encoding='utf-8')
            total += len(raw)
            if total > settings.get('max_characters', 80000):
                raise ValueError('Selected knowledge exceeds the configured budget; narrow dashboard selection. No documents were truncated.')
            pack = json.loads(raw)
            scoped_views = [v for v in catalog if v['dashboard'] == dashboard_key]
            view_documents = set()
            for view in scoped_views:
                matches = [record for record in pack.get('views', []) if record.get('view_name') == view['name']
                           and record.get('workbook_content_url') == view.get('workbook_content_url')]
                if len(matches) > 1:
                    raise ValueError('Duplicate knowledge identity for discovered view.')
                if matches:
                    self._validate_contract(matches[0])
                    self.records[(dashboard_key, view['id'])] = matches[0]
                    if matches[0].get('source_document'):
                        view_documents.add(matches[0]['source_document'])
            for concept in pack.get('concepts', []):
                # Keep concepts scoped to the selected pack, not a global cross-user cache.
                key = (dashboard_key, concept.get('id'))
                if key in concepts:
                    raise ValueError('Duplicate concept ID in knowledge pack.')
                concepts[key] = {'dashboard': dashboard_key, **concept}
            # All authored business documents for these selected dashboard packs are included.
            # Do not read README, acceptance results, source inventories or raw CSV holdings.
            for folder in ('documents', 'views'):
                for document in sorted((directory / folder).rglob('*.md')):
                    if folder == 'views' and document.relative_to(directory).as_posix() not in view_documents:
                        continue
                    resolved = document.resolve()
                    if not resolved.is_relative_to(directory):
                        raise ValueError('Knowledge document resolves outside its configured pack.')
                    if document.stat().st_size > settings.get('max_characters', 80000) * 4:
                        raise ValueError('Knowledge document exceeds configured capacity.')
                    content = document.read_text(encoding='utf-8')
                    total += len(content)
                    if total > settings.get('max_characters', 80000):
                        raise ValueError('Selected knowledge exceeds budget; no document was truncated.')
                    self.documents.append({'dashboard': dashboard_key, 'reference': document.relative_to(directory).as_posix(), 'content': content})
        self.concepts = list(concepts.values())

    @staticmethod
    def _validate_contract(record):
        if type(record.get('verified_export', False)) is not bool:
            raise ValueError('verified_export must be a JSON boolean.')
        if not isinstance(record.get('columns', {}), dict) or not isinstance(record.get('filters', {}), dict):
            raise ValueError('Invalid knowledge contract.')
        for name, rule in record.get('columns', {}).items():
            if not isinstance(name, str) or rule.get('type') not in ('text', 'number', 'date'):
                raise ValueError('Invalid knowledge column type.')
            if type(rule.get('additive', False)) is not bool:
                raise ValueError('Additivity must be a JSON boolean.')
            if rule.get('date_role', 'unknown') not in ('event', 'reference', 'snapshot', 'unknown'):
                raise ValueError('Invalid configured date role.')
            if rule.get('unit') == 'percentage' and rule.get('additive', False):
                raise ValueError('Percentage additivity is unsupported.')

    def record(self, view):
        return self.records.get((view['dashboard'], view['id']), {})

    def candidates(self, catalog):
        return [{**view, 'business_definition': self.record(view)} for view in catalog]

    def context(self):
        return {'concepts_reference_only': self.concepts, 'business_documents': self.documents,
                'scope': 'Complete configured business documents for selected authorized dashboards; not portfolio-value evidence.'}

    def contract(self, view):
        record = self.record(view)
        return record if record.get('verified_export') else {'columns': {}, 'verified_export': False}

    def references(self, view):
        record = self.record(view)
        return [{'id': 'K1', 'record_id': record.get('record_id'), 'document': record.get('source_document'),
                 'role': 'Business definition only, not evidence of numerical portfolio values.'}] if record else []
