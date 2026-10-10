from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.system import CapabilitiesResponse


router = APIRouter(prefix="/config", tags=["configuration"])


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities(
    settings: Settings = Depends(get_settings),
) -> CapabilitiesResponse:
    return CapabilitiesResponse(
        llm_configured=settings.llm_configured,
        finance_provider_configured=settings.finance_provider_configured,
        database_configured=settings.database_configured,
        demo_mode=settings.demo_mode,
    )

