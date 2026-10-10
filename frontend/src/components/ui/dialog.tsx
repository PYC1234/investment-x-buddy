'use client';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';
export function DetailDialog({ open, onOpenChange, title, description, children }: { open: boolean; onOpenChange: (value: boolean) => void; title: string; description: string; children: ReactNode }) {
  return <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}><DialogPrimitive.Portal><DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-slate-950/25 backdrop-blur-[2px]" /><DialogPrimitive.Content className="dialog-content"><DialogPrimitive.Title className="text-lg font-semibold text-slate-900">{title}</DialogPrimitive.Title><DialogPrimitive.Description className="mt-2 text-xs leading-6 text-slate-500">{description}</DialogPrimitive.Description><div className="mt-6">{children}</div><DialogPrimitive.Close aria-label="关闭详情" className="absolute right-4 top-4 rounded p-1 text-slate-400 hover:bg-slate-100"><X size={18} /></DialogPrimitive.Close></DialogPrimitive.Content></DialogPrimitive.Portal></DialogPrimitive.Root>;
}
