from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings loaded from process variables and the project .env."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    service_name: str = "investment-x-buddy-api"
    version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    demo_mode: bool = True
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"],
        validation_alias="CORS_ORIGINS",
    )

    deepseek_api_key: SecretStr | None = Field(
        default=None, validation_alias="DEEPSEEK_API_KEY"
    )
    deepseek_base_url: str | None = Field(
        default=None, validation_alias="DEEPSEEK_BASE_URL"
    )
    deepseek_model: str | None = Field(
        default=None, validation_alias="DEEPSEEK_MODEL"
    )
    fuyao_api_key: SecretStr | None = Field(
        default=None, validation_alias="FUYAO_API_KEY"
    )
    database_url: SecretStr | None = Field(
        default=None, validation_alias="DATABASE_URL"
    )
    planner_mode: Literal["deepseek", "fixture"] = Field(
        default="deepseek", validation_alias="PLANNER_MODE"
    )
    sqlite_path: Path = Field(
        default=BACKEND_ROOT / "data" / "investment_x_buddy.db",
        validation_alias="SQLITE_PATH",
    )
    max_tool_calls: int = Field(default=8, validation_alias="MAX_TOOL_CALLS")
    max_execution_rounds: int = Field(default=8, validation_alias="MAX_EXECUTION_ROUNDS")
    run_timeout_seconds: float = Field(default=30.0, validation_alias="RUN_TIMEOUT_SECONDS")
    max_tool_retries: int = Field(default=1, validation_alias="MAX_TOOL_RETRIES")
    deepseek_input_cost_per_1m: float | None = Field(
        default=None, validation_alias="DEEPSEEK_INPUT_COST_PER_1M"
    )
    deepseek_output_cost_per_1m: float | None = Field(
        default=None, validation_alias="DEEPSEEK_OUTPUT_COST_PER_1M"
    )

    @staticmethod
    def _has_secret(value: SecretStr | None) -> bool:
        return bool(value and value.get_secret_value().strip())

    @property
    def llm_configured(self) -> bool:
        return all(
            (
                self._has_secret(self.deepseek_api_key),
                bool(self.deepseek_base_url and self.deepseek_base_url.strip()),
                bool(self.deepseek_model and self.deepseek_model.strip()),
            )
        )

    @property
    def finance_provider_configured(self) -> bool:
        return self._has_secret(self.fuyao_api_key)

    @property
    def database_configured(self) -> bool:
        return self._has_secret(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()

