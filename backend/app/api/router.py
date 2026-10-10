from fastapi import APIRouter

from app.api.routes import capabilities, events, health, runs


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(capabilities.router)
api_router.include_router(events.router)
api_router.include_router(runs.router)

