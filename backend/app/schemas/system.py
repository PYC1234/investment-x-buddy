from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    service: str
    status: Literal["ok"]
    version: str
    timestamp: datetime


class CapabilitiesResponse(BaseModel):
    llm_configured: bool
    finance_provider_configured: bool
    database_configured: bool
    demo_mode: bool

