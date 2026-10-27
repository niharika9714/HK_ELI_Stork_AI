import csv
from ..models import Plan, Condition

CATALOG = [{'id': key, 'name': name, 'dashboard': 'hk-sales', 'url': None, 'synthetic': True}
           for key, name in [('holdings', 'Client Holdings'), ('product', 'Product Mix'), ('sector', 'Sector Mix')]]


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
    if 'show' in q and any(w in q for w in ('summary', 'summarize')):
        return Plan(action='native', view_id='holdings', include_summary=True)
    if any(word in q for word in ('pnl', 'return', 'profit', 'coupon', 'risk')):
        return Plan(action='clarify', explanation='This synthetic fixture has no approved metric definition for that question.')
    if any(word in q for word in ('compare', 'comparison', 'heatmap')):
        return Plan(action='analyze', view_id='holdings', dimensions=['Product', 'Sector'], measure='Notional HKD', aggregation='sum', chart='heatmap')
    if 'year' in q or 'month' in q:
        return Plan(action='analyze', view_id='holdings', measure='Notional HKD', aggregation='sum',
                    period='year' if 'year' in q else 'month', date_column='Maturity Date', chart='line')
    if any(word in q for word in ('pie', 'aggregate', 'total', 'summary', 'summarize', 'indicator', 'sub-product')):
        return Plan(action='analyze', view_id='holdings', dimensions=['Product'], measure='Notional HKD', aggregation='sum', chart='pie' if 'pie' in q else 'bar')
    filters = [Condition(column='Status', operator='eq', value='Active')] if 'active' in q else []
    if filters:
        return Plan(action='analyze', view_id='holdings', filters=filters, dimensions=['Product'], measure='Notional HKD', aggregation='sum', chart='bar')
    if any(word in q for word in ('show', 'holdings', 'product', 'sector', 'dashboard')):
        return Plan(action='native', view_id='sector' if 'sector' in q else 'product' if 'product' in q else 'holdings')
    return Plan(action='clarify', explanation='Please name a view, metric, filter or comparison. Demo planning supports the example queries only.')
