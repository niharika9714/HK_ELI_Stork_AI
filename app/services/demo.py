import csv
import json
from ..models import Plan
from ..config import ROOT

FIXTURE = json.loads((ROOT / 'knowledge/mock-ui/scenarios.json').read_text(encoding='utf-8'))
CATALOG = FIXTURE['catalog']


def export(path, count=1000):
    with open(path, 'w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['Client ID', 'Product', 'Sub-product', 'Sector', 'Notional HKD', 'Status', 'Maturity Date'])
        for i in range(count):
            writer.writerow([f'DEMO-{i % 20:03}', ['ELI', 'Note', 'Accumulator'][i % 3],
                             ['A', 'B'][i % 2], ['Technology', 'Finance'][i % 2],
                             (i % 7 + 1) * 1000, 'Active' if i % 2 else 'Matured', f'2027-{i % 12 + 1:02}-15'])


def plan(question):
    q = question.lower()
    for scenario in FIXTURE['scenarios']:
        if all(word in q for word in scenario.get('all', [])) and any(word in q for word in scenario.get('any', [])):
            return Plan.model_validate(scenario['plan'])
    return Plan.model_validate(FIXTURE['fallback'])


def summary_plan(view_id, filters):
    return Plan.model_validate(FIXTURE['summary_plan'] | {'view_id': view_id, 'filters': [f.model_dump() for f in filters]})
