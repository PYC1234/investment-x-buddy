"""Auditable supplemental tools over explicitly imported public-source data.

No guessed vendor endpoints, network fallback, or fabricated valuation history.
An operator imports a validated bundle; requests can only select a stock symbol.
"""
import hashlib
import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.services.tools import RegisteredTool, StockArgs, ToolExecutionError

SUPPLEMENT_TOOLS = {
    'get_valuation_history': ('valuation_history', '历史估值区间'),
    'get_peer_valuations': ('peer_valuations', '同业估值对比'),
    'get_balance_sheet': ('balance_sheets', '资产负债表'),
    'get_cash_flow': ('cash_flows', '现金流量表'),
    'search_company_filings': ('filings', '公告与财报原文'),
}


class SourceRow(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    source: HttpUrl
    as_of: date
    basis: str = Field(min_length=1, max_length=300)

    @model_validator(mode='after')
    def not_future(self):
        if self.as_of > datetime.now(timezone.utc).date():
            raise ValueError('Source date cannot be in the future')
        return self


class ValuationRow(SourceRow):
    pe_ttm: float = Field(gt=0, strict=True)
    pb_mrq: float = Field(gt=0, strict=True)


class PeerRow(ValuationRow):
    symbol: str = Field(pattern=r'^\d{6}\.(SH|SZ)$')
    industry: str = Field(min_length=1, max_length=100)


class BalanceRow(SourceRow):
    period: date
    currency: Literal['CNY'] = 'CNY'
    unit: Literal['元'] = '元'
    total_assets: float = Field(gt=0, strict=True)
    total_liabilities: float = Field(ge=0, strict=True)
    total_equity: float = Field(strict=True)

    @model_validator(mode='after')
    def accounting_identity(self):
        if self.period > self.as_of:
            raise ValueError('Financial period cannot follow source date')
        if not math.isclose(self.total_assets, self.total_liabilities + self.total_equity, rel_tol=1e-5, abs_tol=1):
            raise ValueError('Assets must equal liabilities plus equity')
        return self


class CashRow(SourceRow):
    period: date
    currency: Literal['CNY'] = 'CNY'
    unit: Literal['元'] = '元'
    operating_cash_flow: float = Field(strict=True)
    investing_cash_flow: float = Field(strict=True)
    financing_cash_flow: float = Field(strict=True)

    @model_validator(mode='after')
    def check_period(self):
        if self.period > self.as_of:
            raise ValueError('Financial period cannot follow source date')
        return self


class FilingRow(SourceRow):
    title: str = Field(min_length=1, max_length=200)
    page: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=12000)


class SourceBundle(BaseModel):
    model_config = ConfigDict(extra='forbid')
    symbol: str = Field(pattern=r'^\d{6}\.(SH|SZ)$')
    valuation_history: list[ValuationRow] = Field(default_factory=list, max_length=2000)
    peer_valuations: list[PeerRow] = Field(default_factory=list, max_length=50)
    balance_sheets: list[BalanceRow] = Field(default_factory=list, max_length=20)
    cash_flows: list[CashRow] = Field(default_factory=list, max_length=20)
    filings: list[FilingRow] = Field(default_factory=list, max_length=200)

    @model_validator(mode='after')
    def unique_periods(self):
        for field in ('valuation_history', 'balance_sheets', 'cash_flows'):
            rows = getattr(self, field)
            keys = [getattr(row, 'period', row.as_of) for row in rows]
            if len(keys) != len(set(keys)):
                raise ValueError(f'Duplicate dates in {field}')
        return self


class SourceArgs(StockArgs):
    model_config = ConfigDict(extra='forbid')
    revision: str = Field(pattern=r'^[a-f0-9]{64}$')


class FilingArgs(SourceArgs):
    query: str = Field(default='', max_length=1000)
    limit: int = Field(default=5, ge=1, le=10)


def load_bundle(directory: Path, symbol: str):
    # StockArgs has already constrained symbol; resolve guards CLI callers too.
    target = (directory / f'{symbol}.json').resolve()
    if target.parent != directory.resolve():
        raise ValueError('Invalid source path')
    raw = target.read_bytes()
    if len(raw) > 3 * 1024 * 1024:
        raise ValueError('Source bundle exceeds 3 MB')
    bundle = SourceBundle.model_validate_json(raw)
    if bundle.symbol != symbol:
        raise ValueError('Bundle stock does not match filename')
    return bundle, hashlib.sha256(raw).hexdigest()


def available_sources(directory: Path, symbol: str):
    try:
        bundle, revision = load_bundle(directory, symbol)
    except (OSError, ValueError):
        return {}
    return {tool: {'revision': revision, 'rows': len(getattr(bundle, key))}
            for tool, (key, _) in SUPPLEMENT_TOOLS.items() if getattr(bundle, key)}


def register_source_tools(registry, directory: Path):
    def handler_for(name, key):
        def handler(args):
            try:
                bundle, revision = load_bundle(directory, args.symbol)
            except (OSError, ValueError):
                raise ToolExecutionError('No valid imported public-source bundle for this stock', retryable=False) from None
            if revision != args.revision:
                raise ToolExecutionError('Source revision changed; create a new plan and approve again', retryable=False)
            rows = sorted(getattr(bundle, key), key=lambda r: getattr(r, 'period', r.as_of))
            if not rows:
                raise ToolExecutionError('Requested dataset is not available in the imported bundle', retryable=False)
            total_rows = len(rows)
            if key == 'filings':
                terms = set(re.findall(r'[a-zA-Z0-9]{2,}|[\u4e00-\u9fff]{2,}', args.query.lower()))
                terms |= {term[i:i+2] for term in list(terms) if re.search(r'[\u4e00-\u9fff]', term) for i in range(len(term)-1)}
                def score(row):
                    text = (row.title + ' ' + row.text).lower()
                    return sum(text.count(term) for term in terms)
                rows = sorted(rows, key=lambda row: (score(row), row.as_of), reverse=True)
                rows = [row for row in rows if not terms or score(row) > 0][:args.limit]
                if not rows:
                    raise ToolExecutionError('No relevant filing passages found in the imported corpus', retryable=False)
            result = {'symbol': args.symbol, 'available': True, 'is_demo': False,
                      'data_label': 'IMPORTED PUBLIC SOURCES', 'source': str(rows[0].source),
                      'retrieved_at': datetime.now(timezone.utc).isoformat(), 'currency': 'CNY',
                      'revision': revision, 'dataset': key, 'records': [r.model_dump(mode='json') for r in rows],
                      'total_imported_rows': total_rows, 'retrieval_method': 'keyword' if key == 'filings' else 'all_rows',
                      'quality': {'status': 'WARN', 'usable': True, 'issues': [
                          {'code': 'IMPORTED_SOURCE_NOT_VERIFIED', 'message': '已校验结构与口径；导入内容及来源真实性仍需人工核验。', 'severity': 'WARN'}]}}
            if key == 'valuation_history':
                values = [r.pe_ttm for r in rows]
                result['statistics'] = {'count': len(values), 'min_pe_ttm': min(values), 'max_pe_ttm': max(values)}
            result['missing_information'] = '仅覆盖已导入样本，未保证完整性、行业可比性或最新性；不据此给出目标价。'
            return result
        return handler
    for name, (key, label) in SUPPLEMENT_TOOLS.items():
        registry.register(RegisteredTool(name, f'{label}；仅从已导入且版本绑定的公开资料读取。无数据时不可用，不联网补造。',
                                         FilingArgs if key == 'filings' else SourceArgs, handler_for(name, key), 'IMPORTED PUBLIC SOURCES',
                                         capability=key, limitation='需要事先导入该标的真实资料；不得视为已独立核验'))
