import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@pytest.mark.anyio
async def test_unexpected_error_is_sanitized_and_secret_is_not_logged(
    test_settings: Settings, caplog
) -> None:
    app = create_app(test_settings)
    secret_marker = "test-only-secret"

    @app.get("/test-only/boom")
    async def boom() -> None:
        raise RuntimeError(secret_marker)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    with caplog.at_level(logging.ERROR):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/test-only/boom")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_server_error"
    assert secret_marker not in response.text
    assert secret_marker not in caplog.text

