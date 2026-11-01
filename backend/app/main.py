import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    from app.services.runs import get_run_service, build_run_service
    from app.services.jobs import worker_loop

    @asynccontextmanager
    async def lifespan(application):
        factory = application.dependency_overrides.get(get_run_service, get_run_service)
        worker = asyncio.create_task(worker_loop(factory())) if active_settings.worker_enabled and active_settings.execution_mode == 'queued' else None
        try:
            yield
        finally:
            if worker:
                worker.cancel()
                try:
                    await worker
                except asyncio.CancelledError:
                    pass

    app = FastAPI(
        title="Investment X Buddy API",
        version=active_settings.version,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: active_settings
        service = None
        def resolve_service():
            nonlocal service
            if service is None:
                service = build_run_service(active_settings)
            return service
        app.dependency_overrides[get_run_service] = resolve_service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Authorization", "Content-Type", "Last-Event-ID"],
    )
    register_error_handlers(app)
    @app.middleware('http')
    async def private_cache_headers(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(active_settings.api_v1_prefix) and request.url.path != active_settings.api_v1_prefix + '/events/demo':
            response.headers['Cache-Control'] = 'no-store'
        return response
    app.include_router(api_router, prefix=active_settings.api_v1_prefix)
    return app


app = create_app()

