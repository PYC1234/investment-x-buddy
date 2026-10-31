from fastapi import APIRouter

from app.api.routes import capabilities, events, health, runs
from app.api.routes import documents


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(capabilities.router)
api_router.include_router(events.router)
api_router.include_router(runs.router)
api_router.include_router(documents.router)

