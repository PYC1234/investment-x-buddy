import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def test_settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        sqlite_path=tmp_path / 'auth-test.db',
        deepseek_api_key="test-only-secret",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-flash",
        fuyao_api_key=None,
        database_url=None,
    )


@pytest.fixture
def app(test_settings: Settings) -> FastAPI:
    return create_app(test_settings)


@pytest.fixture
async def client(app: FastAPI):
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        token = (await test_client.post('/api/v1/auth/guest')).json()['token']
        test_client.headers['Authorization'] = 'Bearer ' + token
        yield test_client


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"

