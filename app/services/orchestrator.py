from tempfile import TemporaryDirectory
from pathlib import Path
from ..integrations.tableau import Tableau
from ..integrations import stork
from . import demo
from .identity import authorize
from .analysis import Analysis
from .knowledge import Knowledge


def analytical_result(config, client, view, dashboard, question, decision, is_demo, knowledge=None):
    knowledge = knowledge or Knowledge(config, [dashboard], [view], demo=is_demo)
    with TemporaryDirectory(prefix='hkeli-analysis-') as directory:
        path = Path(directory) / 'authorized.csv'
        if is_demo:
            demo.export(path)
        else:
            client.export(view, path)
        analysis = Analysis(path, config, knowledge.contract(view))
        try:
            if not is_demo:
                decision = stork.plan(config, question, knowledge.candidates([view]), analysis.profile(), knowledge=knowledge.context())
                if decision.action == 'clarify':
                    raise ValueError(decision.explanation)
                if decision.action != 'analyze' or decision.view_id != view['id']:
                    raise ValueError('Analysis decision changed the authorized source or execution path.')
            return analysis.execute(decision), decision
        finally:
            analysis.close()


def run(config, user, selected, question):
    dashboards = authorize(config, user, selected)
    is_demo = config['app']['mode'] == 'demo'
    client = None if is_demo else Tableau(config, user)
    catalog = [v for v in demo.CATALOG if v['dashboard'] in selected] if is_demo else client.catalog(dashboards)
    if not catalog:
        return {'status': 'missing_data', 'message': 'No configured published views were discovered in your selected authorized dashboards.', 'citations': []}
    knowledge = Knowledge(config, dashboards, catalog, demo=is_demo)
    decision = demo.plan(question) if is_demo else stork.plan(config, question, knowledge.candidates(catalog), knowledge=knowledge.context())
    if decision.action == 'clarify':
        return {'status': 'clarification', 'message': decision.explanation, 'citations': [], 'synthetic': is_demo}
    view = next((v for v in catalog if v['id'] == decision.view_id and (is_demo or v['dashboard'] == decision.dashboard)), None)
    if not view:
        raise ValueError('Model selected a view outside the selected authorized dashboards.')
    dashboard = next(d for d in dashboards if d['key'] == view['dashboard'])
    source_selection = decision.model_dump()
    citation = {'id': 'T1', 'title': view['name'], 'url': view['url'], 'synthetic': is_demo,
                'scope': 'Published view under the authenticated Tableau identity.' if not is_demo else 'Synthetic demo fixture, not a Tableau export.'}
    if decision.action == 'native' and (decision.aggregation != 'none' or decision.period or decision.dimensions or decision.measure):
        raise ValueError('Native decision includes unexecuted analytical operations.')
    if decision.action == 'native':
        for condition in decision.filters:
            allowed = knowledge.contract(view).get('filters', {}).get(condition.column, [])
            if condition.operator != 'eq' or condition.value not in allowed:
                raise ValueError('Requested native filter is not declared supported; no unfiltered substitute was produced.')
        if is_demo:
            response = {'status': 'demo_native', 'message': 'Synthetic preview of the selected view. Live mode embeds the original Tableau view. [T1]',
                    'visual': {'type': 'demo_native', 'title': view['name']}, 'citations': [citation], 'synthetic': True}
        else:
            response = {'status': 'native', 'message': 'Original authorized Tableau view. [T1]', 'citations': [citation],
                'visual': {'type': 'tableau', 'url': view['url'], 'title': view['name'],
                           'filters': [c.model_dump() for c in decision.filters]}, 'view_id': view['id'], 'dashboard_key': dashboard['key']}
        if decision.include_summary:
            try:
                from ..models import Plan
                summary_plan = demo.summary_plan(view['id'], decision.filters) if is_demo else Plan(action='analyze', view_id=view['id'], filters=decision.filters)
                result, _ = analytical_result(config, client, view, dashboard, question, summary_plan, is_demo, knowledge=knowledge)
                # Never attach a summary over a different filter scope than the native chart.
                if not is_demo and _.filters != decision.filters:
                    raise ValueError('Analysis filter scope differs from the displayed chart.')
                response['result'] = result
            except Exception:
                response['analysis_error'] = 'Optional analysis unavailable; the original authorized view remains available.'
        response['definition_references'] = knowledge.references(view)
        response['source_selection'] = source_selection
        return response
    try:
        result, decision = analytical_result(config, client, view, dashboard, question, decision, is_demo, knowledge=knowledge)
        return {'status': 'analysis', 'message': 'Results calculated from the cited source over all ' + str(result['input_rows']) + ' received rows. [T1]',
                'result': result, 'plan': decision.model_dump(), 'citations': [citation], 'synthetic': is_demo,
                'definition_references': knowledge.references(view), 'source_selection': source_selection}
    except ValueError as error:
        return {'status': 'missing_data_or_unsupported_operation', 'message': str(error), 'citations': [citation], 'synthetic': is_demo}
