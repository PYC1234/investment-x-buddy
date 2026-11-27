'use client';

import { useState } from 'react';
import { ArrowRight, ArrowUpRight, FileText, Menu, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DetailDialog } from '@/components/ui/dialog';

const filing = 'https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF';

export function ResearchWelcome({ onStart, onUpload, onMenu }: { onStart: () => void; onUpload: () => void; onMenu: () => void }) {
  const [sampleOpen, setSampleOpen] = useState(false);
  return <section className="research-welcome" aria-labelledby="welcome-title">
    <div>
      <Button className="mobile-only mb-3" size="icon" variant="ghost" onClick={onMenu} aria-label="打开研究侧栏"><Menu /></Button>
      <h1 id="welcome-title">A 股投研工作台</h1>
      <p>查行情、估值和财报，核对数据口径与原文。也可以上传 PDF 或 CSV，直接针对手里的资料提问。</p>
      <div className="flex flex-wrap gap-2">
        <Button type="button" onClick={onStart}>开始 A 股研究 <ArrowRight size={15} /></Button>
        <Button type="button" variant="outline" onClick={onUpload}><Upload size={15} /> 上传资料分析</Button>
      </div>
    </div>
    <div className="welcome-example">
      <h2>示例 · 贵州茅台（600519.SH）</h2>
      <p>2025 年经营现金流为什么下降？</p>
      <p><strong>同比下降 33.46%</strong> <a href={`${filing}#page=9`} target="_blank" rel="noreferrer">财报第 9 页 <ArrowUpRight size={12} /></a></p>
      <p>年报解释：集团成员单位存款减少，且不可随时支取的同业存款增加。 <a href={`${filing}#page=10`} target="_blank" rel="noreferrer">财报第 10 页 <ArrowUpRight size={12} /></a></p>
      <Button type="button" variant="outline" size="sm" onClick={() => setSampleOpen(true)}><FileText size={14} /> 查看示例报告</Button>
    </div>
    <DetailDialog open={sampleOpen} onOpenChange={setSampleOpen} title="贵州茅台 2025 年现金流" description="示例报告 · 根据公司公开年报整理">
      <div className="space-y-4 text-sm leading-relaxed">
        <section>
          <h3 className="font-semibold">经营现金流净额下降 33.46%</h3>
          <p>由 2024 年的 924.64 亿元降至 2025 年的 615.22 亿元。两期均为全年合并口径。 <a className="underline" href={`${filing}#page=9`} target="_blank" rel="noreferrer">查看第 9 页变动表</a></p>
        </section>
        <section>
          <h3 className="font-semibold">公司披露的原因</h3>
          <p>公司将下降主要归因于旗下财务公司吸收的集团成员单位存款减少，以及不可随时支取的同业存款增加。</p>
          <blockquote className="my-2 border-l-2 border-slate-300 bg-slate-50 p-3">「……吸收集团公司成员单位存款减少及不可随时支取的同业存款增加。」</blockquote>
          <a className="underline" href={`${filing}#page=10`} target="_blank" rel="noreferrer">查看第 10 页管理层原文</a>
        </section>
        <section>
          <h3 className="font-semibold">还有什么无法判断</h3>
          <p>这段披露没有量化两项因素各自的影响。单凭这条解释，无法判断酒类业务的回款变化。</p>
        </section>
      </div>
    </DetailDialog>
  </section>;
}
