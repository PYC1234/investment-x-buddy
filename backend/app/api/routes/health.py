from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.system import HealthResponse


router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        service=settings.service_name,
        status="ok",
        version=settings.version,
        timestamp=datetime.now(timezone.utc),
    )

