"""Deterministic research coverage review, not an LLM correctness verdict."""
from app.services.annual_update import filing_arguments
from app.services.fuyao import FUYAO_STATEMENTS
from app.services.planner import classify_research_goal
from app.services.research_sources import SUPPLEMENT_TOOLS, available_sources


def review_research(goal, tasks, evidence, registry, data_dir, rounds, max_rounds, *, annual_year=None):
    year = annual_year
    focus = "profitability" if year is not None else classify_research_goal(goal)
    requirements = {
        'profitability': ['get_financial_summary', 'get_cash_flow', 'get_balance_sheet'],
        'valuation': ['get_valuation_snapshot', 'get_financial_summary', 'get_valuation_history', 'get_peer_valuations'],
        'risk': ['get_market_snapshot', 'get_balance_sheet', 'get_cash_flow', 'search_company_filings'],
        'comprehensive': ['get_market_snapshot', 'get_financial_summary', 'get_valuation_snapshot', *SUPPLEMENT_TOOLS],
    }[focus]
    if year is not None:
        requirements = ['get_financial_summary', 'search_company_filings']
    usable = {e['tool_name'] for e in evidence if e['data'].get('available', True)
              and e['data'].get('quality', {}).get('usable', True)
              and (year is None or (not e['is_demo'] and str(e['data'].get('fiscal_year')) == str(year)))}
    if year is not None and {'read_uploaded_annual_report', 'find_official_annual_report'} & usable:
        usable.add('search_company_filings')
    if year is None:
        income_years = {str(item['data'].get('fiscal_year')) for item in evidence
                        if item['tool_name'] == 'get_financial_summary'
                        and item['data'].get('quality', {}).get('usable', True)
                        and item['data'].get('available', True)}
        for item in evidence:
            name = item['tool_name']
            if name in usable and name in FUYAO_STATEMENTS:
                dataset = FUYAO_STATEMENTS[name][1]
                if dataset and any(row['period'][:4] in income_years for row in item['data']['records']):
                    usable.update(tool for tool, (key, _) in SUPPLEMENT_TOOLS.items() if key == dataset)
    completed = [name for name in requirements if name in usable]
    missing = [name for name in requirements if name not in usable]
    symbol = next((t['arguments'].get('symbol') for t in tasks if t['arguments'].get('symbol')), None)
    sources = available_sources(data_dir, symbol) if symbol else {}
    planned = {t['tool_name'] for t in tasks}
    proposals = []
    if rounds < max_rounds:
        for name in missing:
            if name in registry.names() and name in sources and name not in planned and len(tasks) + len(proposals) < 8:
                scoped_filing = filing_arguments(sources, symbol, year) if year is not None else None
                if year is not None and not scoped_filing:
                    continue
                label = SUPPLEMENT_TOOLS[name][1]
                proposals.append({'task_key': f'supp_{rounds + 1}_{len(proposals) + 1}', 'title': label,
                                  'tool_name': name, 'arguments': {'symbol': symbol, 'revision': sources[name]['revision']},
                                  'rationale': f'现有证据未覆盖{label}；需要用户批准后读取已导入资料。',
                                  'question': label, 'evidence_required': ['来源、时点、口径及版本'],
                                  'completion_criteria': ['取得可用且与标的一致的资料'], 'depends_on': []})
                if name == 'search_company_filings':
                    proposals[-1]['arguments'].update(scoped_filing or {'query': goal, 'limit': 5})
    return {'version': 1, 'research_type': focus,
            'coverage_status': 'SCOPED_EVIDENCE_COLLECTED' if not missing else 'LIMITED',
            'answered_questions': completed, 'unanswered_questions': missing,
            'missing_evidence': [SUPPLEMENT_TOOLS.get(name, ('', name))[1] for name in missing],
            'next_action': 'REQUEST_APPROVAL' if proposals else 'RETRY_OR_STOP' if missing else 'REPORT',
            'proposed_tasks': proposals, 'supplement_rounds': rounds, 'max_supplement_rounds': max_rounds,
            'policy': '规则仅判断证据类别覆盖；不代表已完成事实交叉核验、语义验证或投资判断。'}
