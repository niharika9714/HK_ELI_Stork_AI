import duckdb
import threading
import csv
from pathlib import Path


def identifier(value, columns):
    if value not in columns:
        raise ValueError('Required field is absent from the authorized export: ' + str(value))
    return '"' + value.replace('"', '""') + '"'


class Analysis:
    def __init__(self, path, config, contract):
        self.config, self.contract = config, contract
        self.db = duckdb.connect()
        self._closed = False
        timer = threading.Timer(config['app']['calculation_timeout_seconds'], self.db.interrupt)
        timer.daemon = True
        try:
            if Path(path).stat().st_size > config['app']['max_export_bytes']:
                raise ValueError('CSV exceeds byte capacity; no sampling performed.')
            with open(path, encoding='utf-8-sig', newline='') as stream:
                header = next(csv.reader(stream), [])
            if not header or len(header) != len(set(header)) or any(not name.strip() for name in header):
                raise ValueError('CSV needs unique nonempty headers.')
            self.db.execute('SET memory_limit = ?', [config['app']['duckdb_memory']])
            self.db.execute('SET threads = 1')
            self.db.execute("SET temp_directory = ''")
            timer.start()
            self.db.execute('CREATE TABLE data AS SELECT * FROM read_csv(?, header=true, sample_size=-1)', [str(path)])
            self.columns = {r[0]: r[1] for r in self.db.execute('DESCRIBE data').fetchall()}
            self.count = self.db.execute('SELECT count(*) FROM data').fetchone()[0]
            if self.count > config['app']['max_rows'] or len(self.columns) > config['app'].get('max_columns', 50) or self.count * len(self.columns) > config['app'].get('max_cells', 5000000):
                raise ValueError('Export exceeds row/column/cell capacity; no partial analysis performed.')
            self.definitions = contract.get('columns', {}) if contract.get('verified_export') else {}
            for name, rule in self.definitions.items():
                if name not in self.columns:
                    continue
                kind = self.columns[name]
                if rule['type'] == 'number' and not any(t in kind for t in ('INT', 'DECIMAL', 'DOUBLE', 'FLOAT')):
                    raise ValueError('Received field type conflicts with knowledge contract: ' + name)
                if rule['type'] == 'date' and kind != 'DATE':
                    raise ValueError('Approved date field is not an unambiguous received DATE: ' + name)
            self.additive = [name for name, rule in self.definitions.items() if rule.get('additive') and rule['type'] == 'number' and rule.get('unit') != 'percentage']
            self.dates = [name for name, rule in self.definitions.items() if rule['type'] == 'date']
        except Exception:
            self.close()
            raise
        finally:
            timer.cancel()

    def close(self):
        if not self._closed:
            self._closed = True
            self.db.close()

    def profile(self):
        return {'row_count': self.count, 'columns': self.columns,
                'additive_columns': self.additive,
                'date_columns': self.dates,
                'metric_definitions': self.definitions,
                'grain': self.contract.get('grain', 'Unknown; do not assume positions or deals.'),
                'scope': 'Full received published CSV, not necessarily underlying deals or whole portfolio.'}

    def execute(self, plan):
        timer = threading.Timer(self.config['app']['calculation_timeout_seconds'], self.db.interrupt)
        timer.daemon = True
        timer.start()
        try:
            return self._execute(plan)
        finally:
            timer.cancel()

    def _execute(self, plan):
        columns = self.columns
        dims = [identifier(d, columns) for d in plan.dimensions]
        if len(set(plan.dimensions)) != len(plan.dimensions):
            raise ValueError('Duplicate dimensions.')
        if plan.period:
            if plan.date_column not in self.dates:
                raise ValueError('Calendar aggregation requires an approved date field.')
            field = identifier(plan.date_column, columns)
            dims.append("date_trunc('" + plan.period + "', CAST(" + field + " AS DATE))")
        params, predicates = [], []
        operators = {'eq': '=', 'ne': '<>', 'gt': '>', 'gte': '>=', 'lt': '<', 'lte': '<='}
        for condition in plan.filters:
            predicates.append(identifier(condition.column, columns) + ' ' + operators[condition.operator] + ' ?')
            params.append(condition.value)
        where = ' WHERE ' + ' AND '.join(predicates) if predicates else ''
        if plan.aggregation == 'count':
            raise ValueError('Row counts cannot stand for deals without an approved row-grain definition.')
        if plan.aggregation == 'mean':
            raise ValueError('Mean of a published aggregate needs a verified row-level metric definition.')
        if plan.aggregation == 'sum':
            if plan.measure not in self.additive:
                raise ValueError('Additivity is not approved for this metric.')
            missing = self.db.execute('SELECT count(*) FROM data' + where + (' AND ' if where else ' WHERE ') + identifier(plan.measure, columns) + ' IS NULL', params).fetchone()[0]
            if missing:
                raise ValueError('Missing measure values require an explicit policy; no partial total was produced.')
            for name, kind in columns.items():
                if kind != 'DATE' or name in plan.dimensions:
                    continue
                role = self.definitions.get(name, {}).get('date_role', 'unknown')
                if role in ('snapshot', 'unknown'):
                    distinct = self.db.execute('SELECT count(DISTINCT '+identifier(name, columns)+') FROM data'+where, params).fetchone()[0]
                    if distinct > 1:
                        raise ValueError('Multiple snapshot/unknown dates cannot be rolled into a current total; retain the date or filter one approved date.')
            measure = 'sum(CAST(' + identifier(plan.measure, columns) + ' AS DECIMAL(38,8))) AS value'
        else:
            measure = identifier(plan.measure, columns) + ' AS value' if plan.measure else ''
        selection = ', '.join(dims + ([measure] if measure else [])) or '*'
        group = ' GROUP BY ' + ', '.join(str(i + 1) for i in range(len(dims))) if dims and plan.aggregation == 'sum' else ''
        query = 'SELECT ' + selection + ' FROM data' + where + group
        # Bound output, not input: calculation reads all authorized received rows.
        limit = self.config['app']['max_result_rows']
        result = self.db.execute(query + ' LIMIT ' + str(limit + 1), params)
        names = [d[0] for d in result.description]
        records = result.fetchall()
        if len(records) > limit:
            raise ValueError('Result exceeds display capacity; request a meaningful aggregation. No chart was truncated.')
        rows = [{k: str(v) if v is not None else None for k, v in zip(names, row)} for row in records]
        chart = plan.chart
        if chart != 'table':
            if not plan.measure or not dims or any(v is None for row in rows for v in row.values()):
                raise ValueError('Chart requires complete dimensions and measure; clarify missing-value policy.')
            from decimal import Decimal
            values = [Decimal(row['value']) for row in rows]
            keys = [tuple(row[k] for k in names[:-1]) for row in rows]
            if len(set(keys)) != len(keys):
                raise ValueError('Chart has duplicate dimension keys; specify aggregation.')
            if chart == 'pie' and (len(dims) != 1 or len(rows) > 20 or not values or min(values) < 0
                                   or sum(values) <= 0 or plan.measure not in self.additive):
                raise ValueError('Pie requires one category and a complete nonnegative additive measure with at most 20 slices.')
            if chart == 'heatmap' and (len(dims) != 2 or any(len(set(r[k] for r in rows)) < 2 for k in names[:-1])):
                raise ValueError('Heatmap requires two varying joint dimensions.')
            if chart == 'line' and not plan.period and (len(plan.dimensions) != 1 or plan.dimensions[0] not in self.dates):
                raise ValueError('Line requires one approved date axis.')
        return {'rows': rows, 'columns': names, 'chart': chart, 'input_rows': self.count,
                'measure': plan.measure, 'unit': self.definitions.get(plan.measure, {}).get('unit', 'unknown'),
                'scope': 'Calculated over all received authorized export rows; no sampling.'}
