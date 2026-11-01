'use client';
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { privateFetch, storedIdentity } from '@/lib/identity';
type Source={id:string;filename:string;location:string;text:string};
type Reply={question:string;answer:string;sources:Source[];model_status:string;warnings:string[];history_id?:string};
type Conversation={files:File[];turns:Reply[];historyStart:number;busy:boolean;error:string;useModel:boolean;saveHistory:boolean};
const empty=():Conversation=>({files:[],turns:[],historyStart:0,busy:false,error:'',useModel:false,saveHistory:false});
const sample='产品名称,产品代码,一年收益率,管理费率,风险等级\n示例产品A,000001,3.2%,0.5%,R2\n示例产品B,000002,5.1%,0.8%,R3\n示例产品C,000003,,0.3%,R2\n';
const labels:Record<string,string>={not_requested:'规则提取 · 未调用模型',generated_needs_review:'AI回答 · 请对照来源复核',not_configured:'模型未配置 · 显示规则结果',failed:'AI回答失败 · 显示规则结果'};
function exportReply(reply:Reply){
  const text=`# ${reply.question}\n\n${reply.answer}\n\n## 来源\n`+reply.sources.map(s=>`- [${s.id}] ${s.filename} · ${s.location}：${s.text}`).join('\n');
  const url=URL.createObjectURL(new Blob([text],{type:'text/markdown;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download='资料对话-分析.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
}
export function useDocumentConversation(threadId:string){
  const [conversations,setConversations]=useState<Record<string,Conversation>>({});
  const [signedIn,setSignedIn]=useState(false);
  const controllers=useRef(new Map<string,AbortController>());
  const current=conversations[threadId]??empty();
  const update=(id:string,fn:(value:Conversation)=>Conversation)=>setConversations(all=>({...all,[id]:fn(all[id]??empty())}));
  useEffect(()=>{
    const refresh=()=>setSignedIn(storedIdentity()?.user.kind==='account');
    refresh();window.addEventListener('focus',refresh);
    const running=controllers.current;
    return ()=>{window.removeEventListener('focus',refresh);for(const c of running.values())c.abort();};
  },[]);
  function attach(files:File[]){
    if(current.busy)return;
    const next=[...current.files,...files];
    if(next.length>3||next.some(f=>f.size>3*1024*1024||! /\.(csv|pdf)$/i.test(f.name))){update(threadId,c=>({...c,error:'最多附上3份CSV或PDF，每份不超过3MB。'}));return;}
    update(threadId,c=>({...c,files:next,historyStart:c.turns.length,error:''}));
  }
  async function send(question:string){
    if(current.busy||!current.files.length||controllers.current.has(threadId))return;
    if(current.saveHistory&&storedIdentity()?.user.kind!=='account'){update(threadId,c=>({...c,saveHistory:false,error:'登录已失效，已关闭保存历史；可再次发送，直接匿名分析。'}));setSignedIn(false);return;}
    const id=threadId,snapshot=current,controller=new AbortController();controllers.current.set(id,controller);
    const timer=setTimeout(()=>controller.abort(),180000);update(id,c=>({...c,busy:true,error:''}));
    try{
      const documents=await Promise.all(snapshot.files.map(async file=>{
        const bytes=new Uint8Array(await file.arrayBuffer());let binary='';
        for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
        return {filename:file.name,content_base64:btoa(binary)};
      }));
      const history=snapshot.turns.slice(snapshot.historyStart).slice(-3).flatMap(t=>[{role:'user',content:t.question},{role:'assistant',content:t.answer.slice(0,6000)}]);
      const response=await privateFetch('/api/v1/documents/chat',{method:'POST',signal:controller.signal,body:JSON.stringify({question,documents,history,use_model:snapshot.useModel,save_history:snapshot.saveHistory})});
      const result=await response.json();if(!response.ok)throw new Error(result.error?.message||'资料问答失败，请重试。');
      update(id,c=>({...c,turns:[...c.turns,result]}));
    }catch(error){update(id,c=>({...c,error:error instanceof Error&&error.name==='AbortError'?'已取消或超时，资料和已有回答仍在，可重新发送。':error instanceof Error?error.message:'连接失败，请重试。'}));}
    finally{clearTimeout(timer);controllers.current.delete(id);update(id,c=>({...c,busy:false}));}
  }
  const controls=<div style={{borderTop:'1px solid #e2e8f0',paddingTop:12,fontSize:12,color:'#475569'}}>
    <div style={{display:'flex',flexWrap:'wrap',gap:12,alignItems:'center'}}>
      <label style={{cursor:'pointer',color:'#1d4ed8',fontWeight:600}}>＋ 添加资料（PDF / CSV）<input aria-label="添加对话资料" type="file" accept=".pdf,.csv" multiple disabled={current.busy} style={{display:'none'}} onChange={e=>{attach(Array.from(e.target.files??[]));e.target.value='';}}/></label>
      <button type="button" disabled={current.busy||current.files.length>=3} onClick={()=>attach([new File([sample],'示例产品数据.csv',{type:'text/csv'})])}>试用示例资料</button><span>无需登录 · 不附资料时使用联网研究</span>
    </div>
    {current.files.length>0&&<><ul style={{margin:'10px 0'}}>{current.files.map((file,index)=><li key={index} style={{display:'flex',gap:12,margin:'5px 0'}}><span>📎 {file.name} · {(file.size/1024).toFixed(1)} KB</span><button aria-label={`移除${file.name}`} disabled={current.busy} onClick={()=>update(threadId,c=>({...c,files:c.files.filter((_,i)=>i!==index),historyStart:c.turns.length}))}>移除</button></li>)}</ul>
      <p>本次问题仅分析以上附件，可继续追问。原文件不落盘，资料与对话在当前页面暂存，刷新后清空。</p>
      <label style={{display:'block',marginTop:8}}><input type="checkbox" checked={current.useModel} disabled={current.busy} onChange={e=>update(threadId,c=>({...c,useModel:e.target.checked}))}/> 启用 AI 问答：将资料摘录、问题和最近对话发送给模型，可能产生调用费用。未勾选时仅做规则提取。</label>
      {signedIn?<label style={{display:'block',marginTop:8}}><input type="checkbox" checked={current.saveHistory} disabled={current.busy} onChange={e=>update(threadId,c=>({...c,saveHistory:e.target.checked}))}/> 保存本次问答及引用到我的历史（可选，不保存原文件）</label>:<p style={{marginTop:8}}>匿名不保存个人历史；需要保留结果时可导出，或<Link href="/account">登录后选择保存</Link>。</p>}
    </>}
    {current.error&&<p role="alert" style={{color:'#b91c1c',marginTop:8}}>{current.error}</p>}
    {current.busy&&<p role="status">正在读取当前会话的资料并分析… <button onClick={()=>controllers.current.get(threadId)?.abort()}>取消等待</button></p>}
  </div>;
  const messages=<section aria-label="资料对话" style={{display:'grid',gap:16}}>
    {!current.turns.length&&current.files.length>0&&<div className="input-card"><h3>资料已加入当前对话</h3><p>在上方输入问题，例如“比较这些产品的管理费率，并说明数据缺失情况”，然后发送。启用 AI 问答后可继续追问。</p></div>}
    {current.turns.map((turn,index)=><article className="input-card" key={index}>
      <h3 style={{fontWeight:600,marginBottom:12}}>你：{turn.question}</h3><p style={{fontSize:12,color:'#64748b',marginBottom:10}}>{labels[turn.model_status]} · {turn.history_id?'已保存到我的历史':'未保存个人历史'}</p>
      <div style={{whiteSpace:'pre-wrap',lineHeight:1.8,overflowWrap:'anywhere'}}>{turn.answer}</div>
      {turn.warnings.map((warning,i)=><p key={i} role="status" style={{color:'#92400e',marginTop:8}}>{warning}</p>)}
      <details style={{marginTop:16}}><summary style={{cursor:'pointer',fontWeight:600}}>查看本轮原文来源（{turn.sources.length}）</summary>{turn.sources.map(source=><details key={source.id} style={{marginTop:10}}><summary style={{cursor:'pointer'}}>[{source.id}] {source.filename} · {source.location}</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',fontFamily:'inherit',fontSize:12,marginTop:8}}>{source.text}</pre></details>)}</details>
      <button style={{marginTop:16,color:'#1d4ed8'}} onClick={()=>exportReply(turn)}>导出本轮回答与来源</button>
    </article>)}
  </section>;
  return {hasDocuments:current.files.length>0,hasMessages:current.turns.length>0,busy:current.busy,send,controls,messages};
}
