export type RunStatus = 'idle' | 'running' | 'approval' | 'paused' | 'completed' | 'partial' | 'cancelled' | 'failed' | 'rejected';
export type WorkspaceTab = 'Research' | 'Plan' | 'Trace';
export type DataState = 'ready' | 'loading' | 'empty';
export type ApiRunStatus = 'PLANNING' | 'PENDING_APPROVAL' | 'APPROVED' | 'RUNNING' | 'COMPLETE' | 'PARTIAL' | 'FAILED' | 'REJECTED' | 'CANCELLED';
export interface TraceEvent { id: number | string; time: string; title: string; detail: string; kind: 'info' | 'success' | 'warning' | 'error'; tokens: number; latency: number }
export interface Checkpoint { step: number; calls: number; tokens: number; latency: number; approval: 'pending' | 'approved' | 'rejected'; sequence?: number; beforeChars?: number; afterChars?: number }
export interface ResearchTask { id: string; position: number; title: string; toolName: string; arguments: Record<string, unknown>; rationale: string; status: string; attempts: number; evidenceId: string | null; error: string | null }
export interface ResearchEvidence { id: string; title: string; type: string; period: string; detail: string; limitation: string; isDemo: boolean; toolName: string; data: Record<string, unknown> }
export interface ResearchFinding { task: string; statement: string; evidenceIds: string[] }
export interface ResearchReportData { title: string; status: string; dataNotice: string; executiveSummary: string; findings: ResearchFinding[]; missingInformation: string[]; evidenceIds: string[] }
export interface ToolCall { id: string; toolName: string; attempt: number; status: string; durationMs: number; error: string | null }
export interface ToolDefinition { name: string; description: string; permission: string; parameters?: Record<string, unknown> }
export interface ResearchThread {
  id: string; remoteRunId?: string; remoteThreadId?: string; title: string; company: string; code: string; sector: string; goal: string;
  status: RunStatus; step: number; approval: 'pending' | 'approved' | 'rejected';
  tab: WorkspaceTab; events: TraceEvent[]; calls: number; tokens: number; latency: number;
  updated: string; checkpoint: Checkpoint | null; recovered: boolean;
  researchScope?: { type: string; scope: string[]; limitations: string[] };
  apiStatus?: ApiRunStatus; planVersion?: number; plannerMode?: string; loading?: boolean;
  tasks?: ResearchTask[]; apiEvidence?: ResearchEvidence[]; apiReport?: ResearchReportData | null;
  toolCalls?: ToolCall[]; apiTools?: ToolDefinition[]; memory?: Record<string, unknown>;
  costUsd?: number | null; costStatus?: string; apiDataset?: Dataset | null;
}
export interface Dataset { isDemo?: boolean; metrics: { label: string; value: string; unit: string; note: string }[]; prices: { date: string; price: number }[]; financials: { year: string; revenue: number; profit: number }[]; findings: string[] }
export interface Preferences { horizon: string; risk: string; evidence: boolean }
export type RunAction = { type: 'START'; goal: string } | { type: 'TICK' | 'PAUSE' | 'RESUME' | 'CANCEL' | 'APPROVE' | 'REJECT' | 'FAIL' | 'RECOVER'; time: string };
