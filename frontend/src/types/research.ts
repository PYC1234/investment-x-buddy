export type RunStatus = 'idle' | 'running' | 'approval' | 'paused' | 'completed' | 'partial' | 'cancelled' | 'failed' | 'rejected';
export type WorkspaceTab = 'Research' | 'Plan' | 'Trace';
export type DataState = 'ready' | 'loading' | 'empty';
export type ApiRunStatus = 'PLANNING' | 'PENDING_APPROVAL' | 'APPROVED' | 'RUNNING' | 'COMPLETE' | 'PARTIAL' | 'FAILED' | 'REJECTED' | 'CANCELLED';
export interface TraceEvent { id: number | string; time: string; title: string; detail: string; kind: 'info' | 'success' | 'warning' | 'error'; tokens: number; latency: number }
export interface Checkpoint { step: number; calls: number; tokens: number; latency: number; approval: 'pending' | 'approved' | 'rejected'; sequence?: number; beforeChars?: number; afterChars?: number }
export interface ResearchTask { id: string; position: number; title: string; toolName: string; arguments: Record<string, unknown>; rationale: string; status: string; attempts: number; evidenceId: string | null; error: string | null; taskKey?: string; dependsOn?: string[]; question?: string; completionCriteria?: string[] }
export interface ResearchEvidence { id: string; title: string; type: string; period: string; detail: string; limitation: string; isDemo: boolean; toolName: string; data: Record<string, unknown> }
export interface FindingClaim { evidence_id: string; field: string; base_field?: string; value: number; raw_value: number; base_value?: number | null; base_multiplier?: number; formula: string; period?: string | number | null; comparison_period?: string; unit: string; basis: string; page?: number; source?: string }
export interface FilingRef { evidence_id: string; record_index: number; collection?: 'reasons' }
export interface FindingDetails { kind?: 'disclosed' | 'computed' | 'observed' | 'gap' | 'interpretation'; claims?: FindingClaim[]; limitations?: string[]; excerpt_refs?: FilingRef[]; source_links?: Array<{ label: string; url: string }> }
export interface ResearchFinding extends FindingDetails { task: string; statement: string; evidenceIds: string[] }
export interface FilingComparison { label: string; period: string; comparison_period: string; current: number; previous: number | null; change: number | null; change_basis: string; change_kind: 'disclosed' | 'computed'; basis: string; evidence_id: string; page: number; source: string }
export interface FollowupAnswer { period: string | null; message: string; findings: ResearchFinding[]; draft_goal: string | null; draft_kind?: 'market' }
export interface ResearchReviewData { coverage_status: string; missing_evidence: string[]; next_action: string; supplement_rounds: number; max_supplement_rounds: number; policy: string }
export interface ReportValidation { status: string; checked_claims: number; semantic_verification: string; policy: string; issues: string[] }
export interface AnnualScope { symbol: string; fiscal_year: number }
export interface PlanRevisionNote { understood: string; added: string[]; removed: string[]; kept: string[] }
export interface AnnualAnswer { label: string; status: 'SUPPORTED' | 'MISSING_DATA' | 'MISSING_COMPARISON' | 'DIRECT_EXCERPT' | 'MISSING_EXPLANATION'; evidence_ids: string[]; excerpt_refs?: Array<{ evidence_id: string; record_index: number }> }
export interface ResearchReportData { annualAnswers?: AnnualAnswer[]; period?: string | null; requestedPeriod?: string; comparisons?: FilingComparison[]; title: string; status: string; qualityStatus?: string; dataNotice: string; executiveSummary: string; findings: ResearchFinding[]; missingInformation: string[]; evidenceIds: string[]; review?: ResearchReviewData; validation?: ReportValidation }
export interface ToolCall { id: string; toolName: string; attempt: number; status: string; durationMs: number; error: string | null }
export interface ToolDefinition { name: string; description: string; permission: string; parameters?: Record<string, unknown> }
export interface ResearchThread {
  id: string; remoteRunId?: string; remoteThreadId?: string; remoteUpdatedAt?: string; title: string; company: string; code: string; sector: string; goal: string;
  status: RunStatus; step: number; approval: 'pending' | 'approved' | 'rejected';
  tab: WorkspaceTab; events: TraceEvent[]; calls: number; tokens: number; latency: number;
  updated: string; checkpoint: Checkpoint | null; recovered: boolean;
  researchScope?: { type: string; scope: string[]; limitations: string[]; revisionNote?: PlanRevisionNote };
  apiStatus?: ApiRunStatus; planVersion?: number; plannerMode?: string; loading?: boolean;
  tasks?: ResearchTask[]; apiEvidence?: ResearchEvidence[]; apiReport?: ResearchReportData | null;
  toolCalls?: ToolCall[]; apiTools?: ToolDefinition[]; memory?: Record<string, unknown>;
  costUsd?: number | null; costStatus?: string; apiDataset?: Dataset | null;
}
export interface Dataset { isDemo?: boolean; metrics: { label: string; value: string; unit: string; note: string }[]; prices: { date: string; price: number }[]; financials: { year: string; revenue: number; profit: number }[]; findings: string[] }
export interface Preferences { horizon: string; risk: string; evidence: boolean }
export type RunAction = { type: 'START'; goal: string } | { type: 'TICK' | 'PAUSE' | 'RESUME' | 'CANCEL' | 'APPROVE' | 'REJECT' | 'FAIL' | 'RECOVER' | 'RETRY_FAILED'; time: string };
