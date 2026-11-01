"""Optional dedicated worker: python -m app.worker (set WORKER_ENABLED=false on API)."""
import asyncio
from app.services.jobs import worker_loop
from app.services.runs import get_run_service

if __name__ == '__main__':
    asyncio.run(worker_loop(get_run_service()))
