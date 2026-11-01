"""Reproducible offline evaluation; no credentials, network, or model calls."""
import argparse
import asyncio
import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import Settings
from app.schemas.research import CreateRunRequest, ApprovalRequest
from app.services.planner import FixturePlanner
from app.services.runs import RunService
from app.services.store import SQLiteStore
from app.services.symbols import SymbolResolutionError
from app.services.tools import build_tool_registry


async def evaluate(cases_path):
    suite = json.loads(Path(cases_path).read_text(encoding='utf-8'))
    results = []
    with tempfile.TemporaryDirectory(prefix='xbuddy-eval-') as temp:
        for case in suite['cases']:
            started = time.perf_counter()
            checks = {}
            settings = Settings(_env_file=None, planner_mode='fixture', execution_mode='inline',
                max_parallel_tools=1, sqlite_path=Path(temp) / f"{case['id']}.db", research_data_dir=Path(temp)/'empty',
                max_tool_calls=case.get('max_tool_calls',8), deepseek_api_key=None, fuyao_api_key=None, database_url=None)
            service = RunService(settings, SQLiteStore(settings.sqlite_path), build_tool_registry(), FixturePlanner())
            try:
                # Exercise the same planner before persistence to distinguish expected clarification.
                await service.planner.plan(case['goal'], {})
                run = await service.create_run(CreateRunRequest(goal=case['goal']))
                checks['expected_clarification'] = 'expected_error' not in case
                checks['plan_scope'] = run['plan']['research_type'] == case.get('focus')
                checks['tool_selection'] = [t['tool_name'] for t in run['tasks']] == case.get('tools')
                run = await service.approve(run['id'], ApprovalRequest(plan_version=1, allowed_tools=list({t['tool_name'] for t in run['tasks']})))
                report = run['report']
                checks['execution_status'] = run['status'] == case.get('expected_status','COMPLETE')
                checks['budget_respected'] = len(service.get_tool_calls(run['id'])) <= settings.max_tool_calls
                ids = {e['id'] for e in service.get_evidence(run['id'])}
                checks['valid_citations'] = all(set(f['evidence_ids']) <= ids for f in report['findings'])
                checks['limitations_disclosed'] = bool(report['missing_information'])
                checks['report_validation'] = report['validation']['status'] == 'RULE_CHECKED'
                usage = run['usage']
            except SymbolResolutionError:
                checks['expected_clarification'] = case.get('expected_error') == 'SymbolResolutionError'
                usage = {'total_tokens':0, 'estimated_cost_usd':0}
            results.append({'id':case['id'], 'passed':all(checks.values()), 'checks':checks,
                            'latency_ms':round((time.perf_counter()-started)*1000,2), 'usage':usage})
    total = len(results)
    return {'suite_version':suite['version'], 'mode':'OFFLINE_FIXTURE_REPLAY', 'created_at':datetime.now(timezone.utc).isoformat(),
            'policy':'Synthetic replay regression; does not establish live model accuracy or user value.',
            'total':total, 'passed':sum(r['passed'] for r in results),
            'pass_rate':sum(r['passed'] for r in results)/total if total else 0, 'results':results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', type=Path, default=Path(__file__).resolve().parents[1]/'evals/research_cases.json')
    parser.add_argument('--output', type=Path, default=Path('evaluation-latest.json'))
    args = parser.parse_args()
    result = asyncio.run(evaluate(args.cases))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Offline regression: {result['passed']}/{result['total']}; {args.output}")
    raise SystemExit(0 if result['passed']==result['total'] else 1)


if __name__ == '__main__':
    main()
