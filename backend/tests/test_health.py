from datetime import datetime

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "investment-x-buddy-api"
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert datetime.fromisoformat(body["timestamp"]).tzinfo is not None


@pytest.mark.anyio
async def test_cors_allows_configured_local_origin_only(client: AsyncClient) -> None:
    allowed = await client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    blocked = await client.options(
        "/api/v1/health",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in blocked.headers


@pytest.mark.anyio
async def test_cors_allows_post_for_configured_frontend(client: AsyncClient) -> None:
    response = await client.options(
        "/api/v1/runs",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"

    loopback_response = await client.options(
        "/api/v1/runs",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert loopback_response.status_code == 200
    assert loopback_response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"

