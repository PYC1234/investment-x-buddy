import { ResearchDashboard } from '@/components/research-dashboard';
import Link from 'next/link';
export default function Home() { return <><Link href="/documents" style={{position:'fixed', bottom:20, right:24, zIndex:50, padding:'10px 18px', borderRadius:10, background:'#087e70', color:'white', boxShadow:'0 4px 20px #0002'}}>公开资料分析 ↗</Link><ResearchDashboard /></>; }
