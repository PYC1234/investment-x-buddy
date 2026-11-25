import type { ResearchEvidence } from '@/types/research';

const number = (value: unknown) => typeof value === 'number' && Number.isFinite(value)
  ? value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
  : '—';

function rows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter(row => row && typeof row === 'object' && !Array.isArray(row))
    : [];
}

export function EvidenceTable({ item }: { item: ResearchEvidence }) {
  const { data } = item;
  const financial = rows(data.financial_history);
  const records = rows(data.records);
  const valuation = data.valuation as Record<string, unknown> | undefined;
  const snapshot = data.snapshot as Record<string, unknown> | undefined;
  const fields: [string, unknown][] = [];
  if (valuation) fields.push(['PE（TTM，倍）', valuation.pe_ttm], ['PB（MRQ，倍）', valuation.pb]);
  if (snapshot) fields.push(['最近可用价（元）', snapshot.price_cny], ['涨跌幅（%）', snapshot.change_percent]);
  if (records.length && data.dataset === 'cash_flows') {
    fields.push(['报告期', records.at(-1)?.period], ['经营活动现金流量净额（元）', records.at(-1)?.operating_cash_flow]);
  }
  if (records.length && data.dataset === 'balance_sheets') {
    const balance = records.at(-1)!;
    fields.push(['报告期', balance.period], ['总资产（元）', balance.total_assets],
      ['总负债（元）', balance.total_liabilities], ['所有者权益（元）', balance.total_equity]);
  }
  const retrieved = typeof data.retrieved_at === 'string' ? new Date(data.retrieved_at) : null;
  return <>
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
      <dt>数据来源</dt><dd>{data.data_label === 'FUYAO / MARKET DATA' ? '扶摇数据接口' : String(data.data_label ?? '见证据记录')}</dd>
      {typeof data.symbol === 'string' && <><dt>标的</dt><dd>{data.symbol}</dd></>}
      <dt>报告期或来源时点</dt><dd>{item.period}</dd>
      {retrieved && Number.isFinite(retrieved.getTime()) && <><dt>取数时间</dt><dd>{retrieved.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })}（北京时间）</dd></>}
      {fields.map(([label, value]) => <div key={label} className="contents"><dt>{label}</dt><dd>{typeof value === 'string' ? value : number(value)}</dd></div>)}
    </dl>
    {financial.length > 0 && <ProfitabilityTable item={item} />}
    <details><summary className="cursor-pointer">本次保存的证据记录</summary><pre className="evidence-json">{item.detail}</pre></details>
  </>;
}

export function ProfitabilityTable({ item, onOpen }: { item: ResearchEvidence; onOpen?: () => void }) {
  const financial = rows(item.data.financial_history);
  if (!financial.length) return null;
  const growth = (value: unknown, prior: unknown) => typeof value === 'number' && typeof prior === 'number' && prior > 0
    ? `${number((value / prior - 1) * 100)}%`
    : '—';
  return <section className="my-3 overflow-x-auto rounded border p-3">
    <h5 className="font-semibold">年度盈利趋势</h5>
    <table className="mt-2 w-full text-sm">
      <thead><tr className="text-left">{['财年', '营收（亿元）', '营收同比', '归母净利润（亿元）', '归母净利润同比'].map(label => <th key={label} scope="col" className="p-1">{label}</th>)}</tr></thead>
      <tbody>{financial.map((row, index) => {
        const previous = financial[index - 1];
        const prior = Number(row.year) === Number(previous?.year) + 1 ? previous : undefined;
        return <tr key={index} className="border-t">
          <th scope="row" className="p-1 text-left">{String(row.year ?? '—')}</th>
          <td className="p-1">{number(row.revenue)}</td><td className="p-1">{growth(row.revenue, prior?.revenue)}</td>
          <td className="p-1">{number(row.profit)}</td><td className="p-1">{growth(row.profit, prior?.profit)}</td>
        </tr>;
      })}</tbody>
    </table>
    <p className="mt-1 text-xs text-slate-600">同比仅比较相邻财年且上年基数为正的记录。</p>
    {onOpen && <button className="citation mt-1" onClick={onOpen}>核对利润表证据</button>}
  </section>;
}
