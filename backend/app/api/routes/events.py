import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse


router = APIRouter(prefix="/events", tags=["events"])


def _encode_sse(event_name: str, sequence: int, message: str) -> str:
    payload = {
        "sequence": sequence,
        "message": message,
        "demo": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"id: {sequence}\nevent: {event_name}\ndata: {data}\n\n"


async def _demo_event_stream(request: Request) -> AsyncIterator[str]:
    events = (
        ("connected", "Demo stream connected."),
        ("step.started", "Demo step started."),
        ("step.completed", "Demo step completed."),
        ("stream.completed", "Demo stream completed."),
    )
    try:
        for sequence, (event_name, message) in enumerate(events, start=1):
            if await request.is_disconnected():
                break
            yield _encode_sse(event_name, sequence, message)
            await asyncio.sleep(0.01)
    except asyncio.CancelledError:
        raise


@router.get("/demo")
async def demo_events(request: Request) -> StreamingResponse:
    return StreamingResponse(
        _demo_event_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

