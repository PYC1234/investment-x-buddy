"""Reusable annual earnings research plan with a pinned company and fiscal year."""
import re

from app.schemas.research import PlannedTask, ResearchPlan
from app.services.research_sources import available_sources


FILING_TOOL = "search_company_filings"
FINANCIAL_TOOL = "get_financial_summary"
EARNINGS_QUERY = "营业收入 归母净利润 盈利 毛利率 变动原因 经营情况"


class AnnualScopeError(ValueError):
    pass


def annual_update_year(goal: str) -> int | None:
    if not re.search(r"财报更新|更新[^，。]{0,18}(?:财报|年报)|(?:财报|年报)[^，。]{0,12}更新", goal):
        return None
    years = set(re.findall(r"(?<![0-9])(20[0-9]{2})(?=\s*年)", goal))
    if len(years) != 1:
        raise AnnualScopeError("请指定一个财年，或使用年度财报更新表单。")
    year = int(years.pop())
    if not 2020 <= year <= 2030:
        raise AnnualScopeError("请选择 2020–2030 范围内的财年。")
    return year


def filing_arguments(sources, symbol, year):
    source = sources.get(FILING_TOOL, {})
    if year not in source.get("fiscal_years", []):
        return None
    return {"symbol": symbol, "fiscal_year": year, "revision": source["revision"],
            "query": EARNINGS_QUERY, "limit": 3}


def build_annual_update(goal, symbol, year, data_dir):
    tasks = [PlannedTask(
        task_key="annual_financials", title=f"{year} 年盈利趋势", tool_name=FINANCIAL_TOOL,
        arguments={"symbol": symbol, "fiscal_year": year, "require_fiscal_year": True},
        rationale="核对指定年度营业收入、归母净利润及可用的上年对照。",
        evidence_required=["指定年度合并利润表", "同口径对照"],
        completion_criteria=["指定年度数据可用；缺少比较期时明确披露"],
    )]
    args = filing_arguments(available_sources(data_dir, symbol), symbol, year)
    if args:
        tasks.append(PlannedTask(
            task_key="annual_filing", title=f"{year} 年报原文", tool_name=FILING_TOOL,
            arguments=args, rationale="在指定年度已导入的年报里寻找盈利和经营变化相关原文。",
            evidence_required=["同一标的及报告年度", "来源链接、页码和原文"],
            completion_criteria=["提供可复核摘录；无法定位的解释明确留空"],
        ))
    limitations = ["管理层原文需人工核对是否支持具体解释；利润趋势不单独支持盈利质量判断。"]
    if not args:
        limitations.append(f"未导入标注 {year} 财年的年报证据；暂无法核对管理层解释。")
    return ResearchPlan(research_goal=goal, research_type="profitability", tasks=tasks,
                        scope=[task.title for task in tasks], limitations=limitations)
