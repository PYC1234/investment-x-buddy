from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    app = FastAPI(
        title="Investment X Buddy API",
        version=active_settings.version,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: active_settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Accept", "Authorization", "Content-Type", "Last-Event-ID"],
    )
    register_error_handlers(app)
    app.include_router(api_router, prefix=active_settings.api_v1_prefix)
    return app


app = create_app()

