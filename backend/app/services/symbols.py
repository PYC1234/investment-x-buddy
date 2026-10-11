"""Small explicit alias list, not a complete security master or fuzzy search."""
import re


class SymbolResolutionError(ValueError):
    pass


ALIASES = {
    "600519.SH": ("贵州茅台", "茅台", "kweichow moutai", "moutai"),
    "300750.SZ": ("宁德时代", "catl"),
    "000001.SZ": ("平安银行",),
    "000858.SZ": ("五粮液",),
    "600036.SH": ("招商银行", "招行"),
    "601318.SH": ("中国平安",),
}


def resolve_symbol(goal: str) -> str:
    codes = set()
    for match in re.finditer(r"(?<![A-Za-z0-9])([0-9]{6})(?:\.(SH|SZ))?(?![A-Za-z0-9.])", goal, re.IGNORECASE):
        code, exchange = match.groups()
        expected = "SH" if code.startswith("6") else "SZ" if code.startswith(("0", "3")) else None
        if not expected or (exchange and exchange.upper() != expected):
            raise SymbolResolutionError("当前只支持沪深 A 股代码，如 600036.SH 或 300750.SZ；请检查代码和交易所。")
        codes.add(f"{code}.{expected}")
    names = {symbol for symbol, aliases in ALIASES.items() if any(alias in goal.lower() for alias in aliases)}
    targets = codes | names
    if len(targets) > 1:
        raise SymbolResolutionError("一次仅支持研究一只股票；名称与代码须一致，请明确单一标的。")
    if not targets:
        raise SymbolResolutionError("未识别研究标的。请填写沪深 A 股六位代码（如 300750.SZ），或使用茅台、宁德时代、平安银行、五粮液、招商银行、中国平安。")
    return targets.pop()
