'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
export default function Documents(){
  const router=useRouter();
  useEffect(()=>{router.replace('/#upload-materials');},[router]);
  return <main style={{padding:32}}><Link href="/#upload-materials">添加 PDF 或 CSV 资料</Link></main>;
}
