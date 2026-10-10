import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@pytest.mark.anyio
async def test_capabilities_report_configuration_without_secrets(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/config/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "llm_configured": True,
        "finance_provider_configured": False,
        "database_configured": False,
        "demo_mode": True,
    }
    serialized = response.text.lower()
    assert "api_key" not in serialized
    assert "database_url" not in serialized
    assert "test-only-secret" not in serialized


@pytest.mark.anyio
async def test_application_starts_without_optional_service_configuration() -> None:
    settings = Settings(
        _env_file=None,
        deepseek_api_key=None,
        deepseek_base_url=None,
        deepseek_model=None,
        fuyao_api_key=None,
        database_url=None,
    )

    transport = ASGITransport(app=create_app(settings), raise_app_exceptions=False)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/config/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "llm_configured": False,
        "finance_provider_configured": False,
        "database_configured": False,
        "demo_mode": True,
    }

