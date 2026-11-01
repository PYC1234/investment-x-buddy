"""SQLite durable queue. Single-host workers, fenced leases, read-only at-least-once calls."""
import asyncio
import logging
import time
from uuid import uuid4

logger = logging.getLogger(__name__)


def enqueue(connection, run_id, retry_ids=None):
    connection.execute(
        "INSERT INTO run_jobs(run_id,state,retry_ids_json,created) VALUES(?,'QUEUED',?,?) "
        "ON CONFLICT(run_id) DO UPDATE SET state='QUEUED',retry_ids_json=excluded.retry_ids_json,"
        "lease_owner=NULL,lease_until=NULL,last_error=NULL",
        (run_id, __import__('json').dumps(sorted(retry_ids)) if retry_ids is not None else None, time.time()),
    )


def claim(service, run_id=None):
    now, token = time.time(), uuid4().hex
    with service.store.connection() as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute(
            "SELECT j.* FROM run_jobs j JOIN runs r ON r.id=j.run_id "
            "WHERE r.status IN ('APPROVED','RUNNING') AND (j.state='QUEUED' OR "
            "(j.state='RUNNING' AND j.lease_until<?)) AND (? IS NULL OR j.run_id=?) "
            "ORDER BY j.created LIMIT 1", (now, run_id, run_id)).fetchone()
        if row is None:
            return None
        if row['state'] == 'RUNNING':
            # Do not charge all lease-expiry downtime as active execution.
            # Account for one uncertain heartbeat interval after the last saved heartbeat.
            elapsed = min(service.settings.worker_lease_seconds / 3,
                          max(0, min(now, row['lease_until']) - (row['heartbeat'] or now)))
            con.execute('UPDATE runs SET execution_seconds=execution_seconds+? WHERE id=?', (elapsed, row['run_id']))
            # Unknown in-flight outcomes are never treated as successful evidence.
            con.execute("UPDATE tool_calls SET status='INTERRUPTED',error='Worker lease expired' WHERE run_id=? AND status='STARTED'", (row['run_id'],))
            con.execute("UPDATE tasks SET status='PENDING' WHERE run_id=? AND status='RUNNING'", (row['run_id'],))
        con.execute("UPDATE run_jobs SET state='RUNNING',lease_owner=?,lease_until=?,heartbeat=? WHERE run_id=?",
                    (token, now + service.settings.worker_lease_seconds, now, row['run_id']))
        return {**dict(row), 'lease_owner': token}


def owns(service, run_id, token):
    row = service.store.fetch_one("SELECT lease_owner,lease_until,state FROM run_jobs WHERE run_id=?", (run_id,))
    return bool(row and row['state'] == 'RUNNING' and row['lease_owner'] == token and row['lease_until'] > time.time())


async def process_one(service, run_id=None):
    job = claim(service, run_id)
    if not job:
        return False
    token, rid = job['lease_owner'], job['run_id']

    async def heartbeat():
        while True:
            await asyncio.sleep(service.settings.worker_lease_seconds / 3)
            with service.store.connection() as con:
                now = time.time()
                previous = con.execute("SELECT heartbeat FROM run_jobs WHERE run_id=? AND lease_owner=? AND state='RUNNING' AND lease_until>?", (rid, token, now)).fetchone()
                if previous is None:
                    return
                con.execute('UPDATE runs SET execution_seconds=execution_seconds+? WHERE id=? AND status=\'RUNNING\'', (max(0, now - previous['heartbeat']), rid))
                con.execute("UPDATE run_jobs SET lease_until=?,heartbeat=? WHERE run_id=? AND lease_owner=? AND state='RUNNING' AND lease_until>?",
                            (now + service.settings.worker_lease_seconds, now, rid, token, now))

    beating = asyncio.create_task(heartbeat())
    try:
        retry = __import__('json').loads(job['retry_ids_json']) if job['retry_ids_json'] is not None else None
        result = await service.execute(rid, set(retry) if retry is not None else None, lease_token=token)
        if retry is not None and result['status'] not in {'APPROVED','RUNNING','CANCELLED'}:
            service._event(rid, 'run.retry_completed', {'status': result['status'], 'task_ids': retry})
        with service.store.connection() as con:
            con.execute("UPDATE run_jobs SET state='DONE',lease_until=NULL WHERE run_id=? AND lease_owner=? AND state='RUNNING'", (rid, token))
    except asyncio.CancelledError:
        # Leave a leased job for another worker to reclaim after expiration.
        raise
    except Exception as exc:
        logger.error('Research worker failed: %s', type(exc).__name__)
        with service.store.connection() as con:
            con.execute("UPDATE runs SET status='FAILED',error='worker_execution_failed' WHERE id=? AND EXISTS(SELECT 1 FROM run_jobs WHERE run_id=? AND lease_owner=?) AND status!='CANCELLED'", (rid, rid, token))
            con.execute("UPDATE run_jobs SET state='FAILED',last_error=?,lease_until=NULL WHERE run_id=? AND lease_owner=?", (type(exc).__name__, rid, token))
    finally:
        beating.cancel()
        try:
            await beating
        except asyncio.CancelledError:
            pass
    return True


async def worker_loop(service):
    while True:
        try:
            if not await process_one(service):
                await asyncio.sleep(service.settings.worker_poll_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error('Queue unavailable: %s', type(exc).__name__)
            await asyncio.sleep(service.settings.worker_poll_seconds)
