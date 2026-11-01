"""Bounded dependency-aware executor with durable call reservation and lease fencing."""
import asyncio
import json
import time
from uuid import uuid4

from app.core.errors import AppError
from app.services.evidence_quality import assess_evidence
from app.services.jobs import owns
from app.services.tools import ToolExecutionError


class LeaseLost(Exception):
    pass


def fence(con, run_id, token):
    row = con.execute("SELECT j.lease_owner,j.lease_until,j.state,r.status FROM run_jobs j JOIN runs r ON r.id=j.run_id WHERE j.run_id=?", (run_id,)).fetchone()
    if not row or row['lease_owner'] != token or row['lease_until'] <= time.time() or row['state'] != 'RUNNING' or row['status'] != 'RUNNING':
        raise LeaseLost()


async def execute(service, run_id, retry_ids, token):
    from app.services.runs import now_iso
    run = service._run_or_404(run_id)
    approval = run.get('approval')
    if not approval or approval.get('plan_version') != run['plan_version']:
        raise AppError(status_code=409, code='approval_required', message='A matching plan approval is required.')
    if run['status'] not in {'APPROVED', 'RUNNING'} or not owns(service, run_id, token):
        return service.get_run(run_id)
    with service.store.connection() as con:
        con.execute('BEGIN IMMEDIATE')
        owned = con.execute("SELECT 1 FROM run_jobs WHERE run_id=? AND lease_owner=? AND state='RUNNING' AND lease_until>?", (run_id, token, time.time())).fetchone()
        if not owned:
            return service.get_run(run_id)
        changed = con.execute("UPDATE runs SET status='RUNNING',started_at=COALESCE(started_at,?),completed_at=NULL,updated_at=? WHERE id=? AND status IN ('APPROVED','RUNNING')", (now_iso(), now_iso(), run_id))
        if changed.rowcount != 1:
            return service.get_run(run_id)
    service._event(run_id, 'execution.started', {'resumed': run['status'] == 'RUNNING'})
    started, spent = time.monotonic(), run['execution_seconds']
    stop_reason = None

    def remaining():
        return service.settings.run_timeout_seconds - spent - (time.monotonic() - started)

    async def one(task):
        allowed = approval['allowed_tools']
        original = (run.get('plan') or {}).get('tasks', [])[task['position'] - 1]
        if (task['plan_version'] != run['plan_version'] or task['tool_name'] not in allowed
                or task['tool_name'] != original['tool_name'] or task['arguments'] != original['arguments']
                or task.get('depends_on', []) != original.get('depends_on', [])):
            service._fail_task(task, 'Task is outside the approved plan version/tool scope.')
            return
        try:
            args = service.registry.validate(task['tool_name'], task['arguments'])
        except ValueError:
            service._fail_task(task, 'Invalid tool arguments')
            return
        initial_attempts = task['attempts']
        maximum = initial_attempts + 1 if retry_ids is not None else service.settings.max_tool_retries + 1
        while task['attempts'] < maximum:
            call_id = str(uuid4())
            with service.store.connection() as con:
                con.execute('BEGIN IMMEDIATE')
                fence(con, run_id, token)
                used = con.execute('SELECT COUNT(*) FROM tool_calls WHERE run_id=?', (run_id,)).fetchone()[0]
                if used >= min(service.settings.max_tool_calls, service.settings.max_execution_rounds) or remaining() <= 0:
                    return
                task['attempts'] += 1
                # Persist the attempt before making the read-only external call.
                con.execute("UPDATE tasks SET status='RUNNING',attempts=?,updated_at=? WHERE id=?", (task['attempts'], now_iso(), task['id']))
                con.execute("INSERT INTO tool_calls(id,run_id,task_id,tool_name,attempt,status,duration_ms,created_at) VALUES(?,?,?,?,?,'STARTED',0,?)",
                            (call_id, run_id, task['id'], task['tool_name'], task['attempts'], now_iso()))
            service._event(run_id, 'tool.started', {'task_id': task['id'], 'tool_name': task['tool_name'], 'attempt': task['attempts']})
            begin = time.perf_counter()
            result, error, retryable = None, None, True
            try:
                result, _ = await asyncio.wait_for(asyncio.to_thread(service.registry.execute, task['tool_name'], args), timeout=max(0.01, remaining()))
                # Imported bundles have their own typed validation and provenance contract.
                if result.get('is_demo') is False and result.get('data_label') != 'IMPORTED PUBLIC SOURCES':
                    result['quality'] = assess_evidence(task['tool_name'], result, task['arguments']['symbol'])
            except asyncio.TimeoutError:
                error = 'Tool timed out; underlying read-only request may finish without being committed'
            except ToolExecutionError as exc:
                error = str(exc)
                retryable = exc.retryable
            except (ValueError, TypeError, KeyError, OSError):
                error = 'Tool response failed validation'
            duration = (time.perf_counter() - begin) * 1000
            with service.store.connection() as con:
                con.execute('BEGIN IMMEDIATE')
                fence(con, run_id, token)
                if result is not None:
                    eid = f'EVD-{uuid4().hex[:12].upper()}'
                    con.execute('INSERT INTO evidence(id,run_id,task_id,tool_name,title,data_json,is_demo,created_at) VALUES(?,?,?,?,?,?,?,?)',
                                (eid, run_id, task['id'], task['tool_name'], task['title'], json.dumps(result, ensure_ascii=False), int(result.get('is_demo', True)), now_iso()))
                    con.execute("UPDATE tasks SET status='COMPLETED',evidence_id=?,error=NULL,updated_at=? WHERE id=?", (eid, now_iso(), task['id']))
                    con.execute("UPDATE tool_calls SET status='SUCCESS',duration_ms=?,result_json=? WHERE id=?", (duration, json.dumps(result, ensure_ascii=False), call_id))
                else:
                    con.execute("UPDATE tool_calls SET status='ERROR',duration_ms=?,error=? WHERE id=?", (duration, error, call_id))
                    con.execute("UPDATE tasks SET status='FAILED',error=?,updated_at=? WHERE id=?", (error, now_iso(), task['id']))
            if result is not None:
                service._event(run_id, 'tool.completed', {'task_id': task['id'], 'tool_name': task['tool_name'], 'evidence_id': eid, 'duration_ms': round(duration, 3)})
                if result.get('quality'):
                    service._event(run_id, 'evidence.quality_checked', {'evidence_id': eid, **result['quality']})
                return
            service._event(run_id, 'tool.failed', {'task_id': task['id'], 'tool_name': task['tool_name'], 'attempt': task['attempts'], 'error': error})
            if not retryable:
                return
        if initial_attempts >= maximum:
            service._fail_task(task, 'Interrupted task exhausted its automatic attempt allowance; explicit retry is required.')

    try:
        attempted = set()
        while True:
            if not owns(service, run_id, token) or service._run_or_404(run_id)['status'] == 'CANCELLED':
                return service.get_run(run_id)
            tasks = service.get_run(run_id)['tasks']
            completed = {t['task_key'] or f"task_{t['position']}" for t in tasks if t['status'] == 'COMPLETED'}
            candidates = [t for t in tasks if t['status'] != 'COMPLETED' and t['id'] not in attempted
                          and (t['id'] in retry_ids if retry_ids is not None else t['status'] not in {'FAILED', 'BLOCKED'})]
            if not candidates:
                break
            if remaining() <= 0:
                stop_reason = 'run_timeout'
                break
            calls = len(service.get_tool_calls(run_id))
            if calls >= min(service.settings.max_tool_calls, service.settings.max_execution_rounds):
                stop_reason = 'max_tool_calls' if calls >= service.settings.max_tool_calls else 'max_execution_rounds'
                break
            ready = [t for t in candidates if set(t.get('depends_on', [])) <= completed]
            if not ready:
                for task in candidates:
                    service.store.execute("UPDATE tasks SET status='BLOCKED',error='Dependency did not complete' WHERE id=?", (task['id'],))
                stop_reason = 'dependency_blocked'
                break
            wave = ready[:service.settings.max_parallel_tools]
            attempted.update(t['id'] for t in wave)
            await asyncio.gather(*(one(task) for task in wave))
            service._save_checkpoint(run_id, 'RUNNING')
        with service.store.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            fence(con, run_id, token)
            con.execute('UPDATE runs SET execution_seconds=? WHERE id=?', (spent + time.monotonic() - started, run_id))
        current = service.get_run(run_id)['tasks']
        evidence = service.get_evidence(run_id)
        partial = any(t['status'] != 'COMPLETED' for t in current) or stop_reason or any(e['data'].get('quality', {}).get('usable') is False for e in evidence)
        status = 'PARTIAL' if partial else 'COMPLETE'
        report = service.finish_report(run_id, status, stop_reason)
        with service.store.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            fence(con, run_id, token)
            con.execute('UPDATE runs SET status=?,report_json=?,error=?,updated_at=?,completed_at=? WHERE id=?',
                        (status, json.dumps(report, ensure_ascii=False), stop_reason, now_iso(), now_iso(), run_id))
        service._event(run_id, 'research.reviewed', report['research_review'])
        service._event(run_id, 'run.completed', {'status': status, 'stop_reason': stop_reason})
        service._save_checkpoint(run_id, status)
        if service.settings.max_supplement_rounds and report['research_review']['proposed_tasks']:
            # Only propose; never execute a changed plan without fresh approval.
            service.propose_supplement(run_id, service._run_or_404(run_id)['updated_at'], run['plan_version'])
        return service.get_run(run_id)
    except LeaseLost:
        return service.get_run(run_id)
