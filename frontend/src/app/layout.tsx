import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Investment X Buddy · AI Research Workspace', description: 'A transparent AI agent workspace for investment research.' };
export default function RootLayout({ children }: { children: React.ReactNode }) { return <html lang="zh-CN"><body>{children}</body></html>; }
