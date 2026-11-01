'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
export default function Documents(){
  const router=useRouter();
  useEffect(()=>{router.replace('/');},[router]);
  return <main style={{padding:32}}><p>资料分析已合并到原来的对话工作台。</p><Link href="/">进入工作台，在输入框下方添加资料 →</Link></main>;
}
