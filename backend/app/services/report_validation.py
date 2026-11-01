"""Field-level provenance and reproducible arithmetic; never certifies free-text reasoning."""
import math
import re
from copy import deepcopy


def read_path(data, path):
    current = data
    for part in path.split('.'):
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def validate_claim(claim, evidence):
    try:
        item = evidence[claim['evidence_id']]
        if not item['data'].get('quality', {}).get('usable', True):
            return False
        value = read_path(item['data'], claim['field'])
        expected = claim['value']
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return False
        if not isinstance(expected, (int, float)) or isinstance(expected, bool) or not math.isfinite(expected):
            return False
        if claim.get('formula') == 'growth_percent':
            base = read_path(item['data'], claim['base_field'])
            if not isinstance(base, (int, float)) or isinstance(base, bool) or not base or not math.isfinite(base):
                return False
            value = (value / base - 1) * 100
        elif claim.get('formula') not in (None, 'identity'):
            return False
        return math.isclose(value, expected, rel_tol=1e-7, abs_tol=1e-7)
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError):
        return False


def attach_validation(report, evidence):
    result = deepcopy(report)
    by_id = {e['id']: e for e in evidence}
    issues = []
    claims = []
    for item in evidence:
        data = item['data']
        paths = [('snapshot.price_cny', 'CNY'), ('snapshot.change_percent', '%'),
                 ('valuation.pe_ttm', '倍'), ('valuation.pb', '倍'),
                 ('financials.roe_percent', '%'), ('financials.net_margin_percent', '%')]
        for index, _ in enumerate(data.get('financial_history', [])):
            paths.extend([(f'financial_history.{index}.revenue', '亿元'), (f'financial_history.{index}.profit', '亿元')])
        for index, row in enumerate(data.get('records', [])):
            paths.extend((f'records.{index}.{key}', row.get('unit', '倍')) for key, value in row.items()
                         if isinstance(value, (int, float)) and key not in {'page'})
        for path, unit in paths:
            try:
                value = read_path(data, path)
            except (KeyError, IndexError, TypeError):
                continue
            claim = {'evidence_id': item['id'], 'field': path, 'value': value, 'unit': unit,
                     'formula': 'identity', 'source': data.get('source', data.get('data_label')),
                     'basis': data.get('field_provenance', {}).get(path, {}).get('basis', '原字段口径'),
                     'time': data.get('timestamp_ms', data.get('fiscal_year'))}
            if validate_claim(claim, by_id):
                claims.append(claim)
        rows = data.get('financial_history', [])
        if len(rows) >= 2 and rows[-2].get('revenue'):
            claim = {'evidence_id': item['id'], 'field': f'financial_history.{len(rows)-1}.revenue',
                     'base_field': f'financial_history.{len(rows)-2}.revenue', 'formula': 'growth_percent',
                     'value': (rows[-1]['revenue'] / rows[-2]['revenue'] - 1) * 100, 'unit': '%',
                     'basis': '相邻可用年度变化；不自动解释为同比或因果关系'}
            if validate_claim(claim, by_id):
                claims.append(claim)
    accepted = []
    for finding in result['findings']:
        refs = finding['evidence_ids']
        if any(ref not in by_id for ref in refs):
            issues.append('已移除引用不存在证据的结论。')
            continue
        if re.search(r'明显低估|建议买入|建议卖出|目标价为\s*\d', finding['statement']):
            issues.append('已拦截当前证据契约不支持的交易或目标价结论。')
            continue
        supplied_claims = finding.get('claims', [])
        if any(not validate_claim(claim, by_id) or claim['evidence_id'] not in refs for claim in supplied_claims):
            issues.append('已移除字段或计算无法复核的结论。')
            continue
        finding['claims'] = supplied_claims or [c for c in claims if c['evidence_id'] in refs]
        finding['validation_scope'] = 'FIELD_AND_ARITHMETIC_ONLY; prose not independently verified'
        accepted.append(finding)
    result['findings'] = accepted
    result['claims'] = claims
    result['validation'] = {'status': 'FAIL' if issues else 'RULE_CHECKED', 'issues': issues,
                            'checked_claims': len(claims), 'semantic_verification': 'NOT_PERFORMED',
                            'policy': '引用存在性、可用字段与公式检查；不保证自然语言推断正确，不代表独立来源核验。'}
    result['missing_information'] = list(dict.fromkeys([*result['missing_information'], *issues]))
    return result
