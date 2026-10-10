import time
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError


class ToolExecutionError(Exception):
    pass


class StockArgs(BaseModel):
    symbol: str = Field(pattern=r"^\d{6}\.(SH|SZ)$")
    simulate_failure: bool = False


class FinancialArgs(StockArgs):
    fiscal_year: int = Field(ge=2020, le=2030)


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[BaseModel], dict[str, Any]]

    def public_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.args_model.model_json_schema(),
            "data_source": "FIXTURE / DEMO DATA",
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        self._tools[tool.name] = tool

    def names(self) -> set[str]:
        return set(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.public_schema() for tool in self._tools.values()]

    def validate(self, name: str, arguments: dict[str, Any]) -> BaseModel:
        if name not in self._tools:
            raise ValueError(f"Tool is not registered: {name}")
        try:
            return self._tools[name].args_model.model_validate(arguments)
        except ValidationError as exc:
            raise ValueError(f"Invalid arguments for {name}: {exc.errors(include_input=False)}") from exc

    def execute(self, name: str, arguments: BaseModel) -> tuple[dict[str, Any], float]:
        started = time.perf_counter()
        result = self._tools[name].handler(arguments)
        return result, (time.perf_counter() - started) * 1000


def _guard_failure(arguments: StockArgs) -> None:
    if arguments.simulate_failure:
        raise ToolExecutionError("Simulated fixture provider failure.")


def market_snapshot(arguments: BaseModel) -> dict[str, Any]:
    values = StockArgs.model_validate(arguments.model_dump())
    _guard_failure(values)
    fixtures = {
        "600519.SH": {"price_cny": 1688.0, "change_percent": 0.62, "as_of": "DEMO-2026-01-02"},
        "000001.SZ": {"price_cny": 11.25, "change_percent": -0.18, "as_of": "DEMO-2026-01-02"},
    }
    return {"data_label": "DEMO DATA", "symbol": values.symbol, "available": values.symbol in fixtures, "snapshot": fixtures.get(values.symbol), "missing_information": None if values.symbol in fixtures else "No fixture market snapshot for this symbol."}


def financial_summary(arguments: BaseModel) -> dict[str, Any]:
    values = FinancialArgs.model_validate(arguments.model_dump())
    _guard_failure(values)
    fixture = {"roe_percent": 31.2, "revenue_growth_percent": 15.7, "net_margin_percent": 49.1} if values.symbol == "600519.SH" and values.fiscal_year == 2025 else None
    return {"data_label": "DEMO DATA", "symbol": values.symbol, "fiscal_year": values.fiscal_year, "available": fixture is not None, "financials": fixture, "missing_information": None if fixture else "No fixture financial statement for this symbol and year."}


def valuation_snapshot(arguments: BaseModel) -> dict[str, Any]:
    values = StockArgs.model_validate(arguments.model_dump())
    _guard_failure(values)
    fixture = {"pe_ttm": 24.6, "pb": 7.8, "dividend_yield_percent": 3.1} if values.symbol == "600519.SH" else None
    return {"data_label": "DEMO DATA", "symbol": values.symbol, "available": fixture is not None, "valuation": fixture, "missing_information": None if fixture else "No fixture valuation data for this symbol."}


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(RegisteredTool("get_market_snapshot", "Return a fixture A-share market snapshot.", StockArgs, market_snapshot))
    registry.register(RegisteredTool("get_financial_summary", "Return fixture annual profitability metrics.", FinancialArgs, financial_summary))
    registry.register(RegisteredTool("get_valuation_snapshot", "Return fixture valuation metrics.", StockArgs, valuation_snapshot))
    return registry

