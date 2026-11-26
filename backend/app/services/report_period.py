"""Interpret financial reporting periods before requesting any data."""
import re
from datetime import datetime, timedelta, timezone


PERIOD_TITLES = {
    "q1": r"(?:第一季度|一季度|一季)报告",
    "h1": r"(?:半年度|半年|中期)报告",
    "q3": r"(?:第三季度|三季度|三季)报告",
    "annual": r"年度报告",
}
PERIOD_MONTHS = {"q1": 3, "h1": 6, "q3": 9, "annual": 12}
PERIOD_NAMES = {"q1": "一季报", "h1": "半年报", "q3": "三季报", "annual": "年报"}
PERIOD_PATTERN = r"(?:第?[一二三四1234]季(?:度|报)|[Qq][1-4]|上半年|半年度|半年报|前三季度|中报)"


def current_date():
    return datetime.now(timezone(timedelta(hours=8))).date()


def report_scope(goal):
    from app.services.annual_update import AnnualScopeError

    years = {int(year) for year in re.findall(r"(?<!\d)(20\d{2})(?=\s*(?:年|[Qq]|[-/]\d))", goal)}
    periods = []
    for pattern, period in (
        (r"第?[一1]季(?:度|报)|Q1", "q1"),
        (r"第?[二2]季(?:度|报)|Q2|上半年|半年度|半年报|中报", "h1"),
        (r"前三季度|第?[三3]季(?:度|报)|Q3", "q3"),
        (r"第?[四4]季(?:度|报)|Q4", "annual"),
    ):
        if re.search(pattern, goal, re.I):
            periods.append(period)
    full_year = bool(re.search(r"完整财年|完整年度|全年|(?<!半)年报|年年度|最近财年|最新财年", goal))
    cash_question = bool(re.search(r"现金|回款|收现|货币资金|合同负债", goal))
    recent_financials = (re.search(r"最近|近期|最新", goal)
                         and re.search(r"经营|业绩|盈利|营收|利润|财报|财务", goal))
    if not (periods or cash_question or full_year or recent_financials):
        return None
    # Annual earnings already has a dedicated plan with annual comparison and filing evidence.
    if full_year and years and not periods and not cash_question and re.search(r"更新|营收|盈利|利润|年报", goal):
        return None
    if len(periods) > 1 or (periods and full_year):
        raise AnnualScopeError("请先选择一个报告期。单份报告可提供其披露的对照期间。")
    if len(years) > 1:
        latest = max(years)
        if years != {latest, latest - 1} or not re.search(r"比|较|对照|对比", goal):
            raise AnnualScopeError("请先指定一个主报告期，可用该报告披露的同期数据作比较。")
    year = max(years) if years else None
    if year is not None and not 2020 <= year <= 2030:
        raise AnnualScopeError("请选择 2020–2030 范围内的报告期。")
    kind = periods[0] if periods else ("annual" if full_year or years else "latest")
    single = bool(re.search(r"单季|当季|仅看(?:第)?[一二三四1234]季度|[Qq][1-4](?![A-Za-z0-9])|第[二三四]季度(?!报告)", goal)
                  or re.search(r"第?[二四24]季度", goal))
    if re.search(r"累计|前三季度|年初至", goal) and not re.search(r"单季|当季", goal):
        single = False
    coverage = "single" if single and kind != "q1" else "reported"
    return {"year": year, "kind": kind, "coverage": coverage}


def period_name(year, kind, coverage="reported"):
    if kind == "latest":
        return "最新已披露财报，执行时确认实际报告期"
    label = PERIOD_NAMES[kind]
    if coverage == "single":
        label += "中的单季数据"
    return f"{year} 年{label}" if year else f"最新已披露{label}"
