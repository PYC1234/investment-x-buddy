'use client';

import { useRef, useState } from 'react';
import Link from 'next/link';
import { documentStyles } from './styles';

type Evidence = { id: string; location: string; text: string };
type Analysis = {
  filename: string; sha256: string; overview: string; markdown: string; duration_ms: number;
  model_status: string; model_summary: string | null; warnings: string[]; evidence: Evidence[];
  fields: {field: string; value: string; evidence_id: string; location: string}[];
  statistics: {column: string; count: number; missing: number; unit: string; min: number; max: number; mean: number; min_source: string; max_source: string}[];
  preview: Record<string, string>[];
};
const base = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, '');
const example = '产品名称,产品代码,一年收益率,管理费率,风险等级\n示例产品A,000001,3.2%,0.5%,R2\n示例产品B,000002,5.1%,0.8%,R3\n示例产品C,000003,,0.3%,R2\n';
const modelLabels: Record<string, string> = {not_requested: '规则分析 · 未调用模型', not_configured: '模型未配置 · 已返回规则分析', generated_needs_review: 'AI摘要已生成 · 请复核', failed: 'AI摘要失败 · 规则结果已保留'};

function download(text: string, filename: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], {type}));
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

export default function Documents() {
  const [files, setFiles] = useState<File[]>([]);
  const [useModel, setUseModel] = useState(false);
  const [results, setResults] = useState<Analysis[]>([]);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState('');
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);

  async function analyze() {
    if (!files.length) return;
    setError(''); setResults([]);
    if (!base) {setError('当前环境尚未连接资料分析服务，请完成后端部署与API地址配置。'); return;}
    if (files.length > 3 || files.some(f => f.size > 3*1024*1024 || !/\.(csv|pdf)$/i.test(f.name))) {
      setError('一次最多3份CSV或PDF，每份不超过3MB。'); return;
    }
    setBusy(true);
    const abort = new AbortController(); controller.current = abort;
    const timeout = setTimeout(() => abort.abort(), 180000);
    try {
      const completed: Analysis[] = [];
      for (const [index, file] of files.entries()) {
        setProgress(`正在分析 ${index+1}/${files.length}：${file.name}`);
        const bytes = new Uint8Array(await file.arrayBuffer());
        let binary = '';
        for (let i=0; i<bytes.length; i+=8192) binary += String.fromCharCode(...bytes.subarray(i, i+8192));
        const response = await fetch(`${base}/api/v1/documents/analyze`, {
          method: 'POST', headers: {'Content-Type': 'application/json'}, signal: abort.signal,
          body: JSON.stringify({filename: file.name, content_base64: btoa(binary), use_model: useModel}),
        });
        const body = await response.json();
        if (!response.ok) throw new Error(`${file.name}：${body.error?.message || body.detail || '分析失败'}`);
        completed.push(body); setResults([...completed]);
      }
      setProgress(`完成 ${completed.length} 份资料。结果仅保留在当前页面，请及时导出。`);
    } catch (e) {
      setError(e instanceof Error && e.name === 'AbortError' ? '任务已取消或超时，已完成的结果保留，可重新分析。' : e instanceof Error ? e.message : '连接失败，请稍后重试。');
    } finally {clearTimeout(timeout); setBusy(false); controller.current = null;}
  }

  function resetSelection(next: File[]) {setFiles(next); setResults([]); setError(''); setProgress('');}

  return <main className="document-workspace">
    <style>{documentStyles}</style>
    <nav><Link href="/">← 返回投资研究</Link><span>XBuddy / 资料分析</span></nav>
    <header><span className="document-eyebrow">DOCUMENT WORKSPACE</span><h1>把资料变成有来源的分析</h1><p>上传公开基金报告或产品数据表，整理字段、比较同列指标，并保留每条结果的出处。</p></header>
    <section className="document-card">
      <h2>1. 选择公开资料</h2>
      <p>CSV支持UTF-8或GB编码、最多5000条记录；PDF支持可复制文字的版本、最多30页。一次最多3份，每份3MB。</p>
      <label className="document-upload">选择 CSV / PDF<input aria-label="选择公开资料" type="file" accept=".csv,.pdf" multiple disabled={busy} onChange={e => resetSelection(Array.from(e.target.files || []))}/></label>
      <button disabled={busy} onClick={() => resetSelection([new File([example], '示例产品数据-非真实产品.csv', {type: 'text/csv'})])}>使用示例数据</button>
      <button onClick={() => download('\uFEFF'+example, '产品对比模板-示例.csv', 'text/csv;charset=utf-8')}>下载CSV模板</button>
      <ul>{files.map((file, i) => <li key={i}>{file.name} · {(file.size/1024).toFixed(1)} KB</li>)}</ul>
      <p className="document-note">文件发送到XBuddy后端进行处理，本功能不落盘、不建立公开文件链接。请仅使用公开资料，不上传客户持仓、身份证件或公司内部文件。</p>
      <label className="document-consent"><input type="checkbox" checked={useModel} disabled={busy} onChange={e=>setUseModel(e.target.checked)}/>额外生成AI摘要：同意将选中的原文片段发送至服务器配置的模型服务，可能产生调用费用。默认关闭。</label>
      <div className="document-actions"><button className="document-primary" onClick={analyze} disabled={busy || !files.length}>{busy ? '正在处理…' : '开始分析'}</button>{busy && <button onClick={()=>controller.current?.abort()}>取消等待</button>}</div>
      <p role="status" aria-live="polite">{progress}</p>{error && <p role="alert" className="document-error">{error}</p>}
    </section>
    {results.length > 1 && <section className="document-card"><h2>本次资料总览</h2><p>各文件独立分析；不同报告的期间、单位和口径尚未自动对齐，不跨文件拼接指标或排名。</p>{results.map((r,i)=><p key={i}><strong>{r.filename}</strong>：{r.overview}</p>)}</section>}
    {results.map((result,index) => <section className="document-card" key={`${index}-${result.sha256}`}>
      <h2>2. {result.filename}</h2><p>{result.overview}</p><p className="document-note">{modelLabels[result.model_status]} · 处理耗时 {result.duration_ms} ms</p>
      <div className="document-actions"><button onClick={()=>download(result.markdown, `${result.filename}-分析.md`, 'text/markdown;charset=utf-8')}>导出报告</button><button onClick={()=>download(JSON.stringify(result,null,2), `${result.filename}-证据.json`, 'application/json')}>导出结构化结果</button></div>
      {result.statistics.length > 0 && <><h3>字段对比</h3><div className="document-table"><table><thead><tr><th>字段 / 单位</th><th>最小值</th><th>最大值</th><th>算术均值</th><th>有效/缺失</th></tr></thead><tbody>{result.statistics.map(s=><tr key={s.column}><td>{s.column} / {s.unit}</td><td>{s.min} [{s.min_source}]</td><td>{s.max} [{s.max_source}]</td><td>{s.mean.toPrecision(5)}</td><td>{s.count} / {s.missing}</td></tr>)}</tbody></table></div></>}
      {result.preview.length > 0 && <details><summary>查看前20条原始记录，核对字段和单位</summary><div className="document-table"><table><thead><tr>{Object.keys(result.preview[0]).map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{result.preview.map((row,i)=><tr key={i}>{Object.values(row).map((v,j)=><td key={j}>{v || '空值'}</td>)}</tr>)}</tbody></table></div></details>}
      {result.model_summary && <><h3>AI摘要（需对照证据复核）</h3><pre className="document-summary">{result.model_summary}</pre></>}
      {result.fields.length > 0 && <><h3>报告明确字段（规则提取，需复核）</h3><ul>{result.fields.map((f,i)=><li key={i}>{f.field}：<strong>{f.value}</strong> [{f.evidence_id}] · {f.location}</li>)}</ul></>}
      <h3>原文证据</h3>{result.evidence.map(e=><details key={e.id}><summary>[{e.id}] {e.location} · {e.text.slice(0,75)}</summary><pre className="document-summary">{e.text}</pre></details>)}
      <h3>范围与待复核项</h3><ul>{result.warnings.map((w,i)=><li key={i}>{w}</li>)}</ul><small className="document-hash">文件指纹：{result.sha256}</small>
    </section>)}
  </main>;
}
