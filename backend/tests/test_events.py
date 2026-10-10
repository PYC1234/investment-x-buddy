import json

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_demo_sse_event_order_and_json_payloads(client: AsyncClient) -> None:
    received: list[tuple[str, dict[str, object]]] = []

    async with client.stream("GET", "/api/v1/events/demo") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache, no-transform"

        current_event: str | None = None
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                current_event = line.removeprefix("event: ")
            elif line.startswith("data: "):
                assert current_event is not None
                payload = json.loads(line.removeprefix("data: "))
                received.append((current_event, payload))
                current_event = None

    assert [event for event, _ in received] == [
        "connected",
        "step.started",
        "step.completed",
        "stream.completed",
    ]
    assert [payload["sequence"] for _, payload in received] == [1, 2, 3, 4]
    assert all(payload["demo"] is True for _, payload in received)
    assert all(isinstance(payload["timestamp"], str) for _, payload in received)

