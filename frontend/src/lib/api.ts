const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const TOKEN_KEY = "cl_session_token";
let sessionToken: string | null = null;
try {
  sessionToken = localStorage.getItem(TOKEN_KEY);
} catch {
  // localStorage 접근 불가 환경(예: 프라이빗 모드) - 로그인 상태 유지 없이 진행
}

export function setSessionToken(token: string | null): void {
  sessionToken = token;
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore
  }
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  return {
    ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
    ...extra,
  };
}

export interface GoogleLoginResponse {
  email: string;
  name: string;
  picture?: string;
  token: string;
}

export async function loginWithGoogle(credential: string): Promise<GoogleLoginResponse> {
  const res = await fetch(`${API_BASE}/auth/google`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ credential }),
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "login failed");
  }
  return res.json();
}

export async function getCurrentUser(): Promise<{ email: string }> {
  const res = await fetch(`${API_BASE}/auth/me`, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "session check failed");
  }
  return res.json();
}

export interface DirectiveOut {
  thread_id: string;
  status: "completed" | "pending_approval" | "pending" | "approved" | "rejected" | "revision";
}

export async function submitDirective(text: string): Promise<DirectiveOut> {
  const res = await fetch(`${API_BASE}/directives`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "directive submission failed");
  }
  return res.json();
}

export async function getDirective(threadId: string): Promise<DirectiveOut> {
  const res = await fetch(`${API_BASE}/directives/${threadId}`, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "directive lookup failed");
  }
  return res.json();
}

export interface TaskOut {
  id: string;
  title: string;
  status: "todo" | "in_progress" | "done";
  dept: string;
  assignee_agent: string;
  start_date: string | null;
  end_date: string | null;
  wbs_parent_id: string | null;
  progress_pct: number;
}

export interface ScheduleOut {
  id: string;
  project_id: string;
  task_id: string;
  calendar_start: string | null;
  calendar_end: string | null;
  task: TaskOut | null;
}

export async function listSchedules(withTask = true): Promise<ScheduleOut[]> {
  const res = await fetch(`${API_BASE}/schedules?with_task=${withTask}`, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "schedule fetch failed");
  }
  return res.json();
}

export async function listTasks(): Promise<TaskOut[]> {
  const res = await fetch(`${API_BASE}/tasks`, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "task fetch failed");
  }
  return res.json();
}

export interface FinanceSummaryPoint {
  period: string;
  expense: number;
}

export async function getFinanceSummary(): Promise<FinanceSummaryPoint[]> {
  const res = await fetch(`${API_BASE}/finance/summary`, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "finance summary fetch failed");
  }
  return res.json();
}

export interface FinanceEntryOut {
  id: string;
  entry_date: string | null;
  debit_account: string;
  credit_account: string;
  amount: number;
  category: string | null;
  vat_flag: boolean;
  merchant: string | null;
  status: "draft" | "confirmed" | "rejected";
  receipt_url: string | null;
}

export async function listFinanceEntries(): Promise<FinanceEntryOut[]> {
  const res = await fetch(`${API_BASE}/finance/entries`, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "finance entries fetch failed");
  }
  return res.json();
}

export interface ReceiptUploadOut {
  finance_entry_id: string;
  status: string;
}

export async function uploadReceipt(file: File): Promise<ReceiptUploadOut> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/finance/receipts`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "receipt upload failed");
  }
  return res.json();
}

export interface MarketingMetricOut {
  id: string;
  product: string;
  channel: string;
  metric_date: string;
  impressions: number;
  clicks: number;
  conversions: number;
  post_id: string | null;
}

export async function getMarketingMetrics(): Promise<MarketingMetricOut[]> {
  const res = await fetch(`${API_BASE}/marketing/metrics`, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "marketing metrics fetch failed");
  }
  return res.json();
}

export interface DeskOut {
  id: string;
  room: string;
  grid_x: number;
  grid_y: number;
  dept: string | null;
  label: string | null;
}

export async function listDesks(): Promise<DeskOut[]> {
  const res = await fetch(`${API_BASE}/office/desks`, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "desk fetch failed");
  }
  return res.json();
}

export async function createDesk(desk: {
  room: string;
  grid_x: number;
  grid_y: number;
  dept?: string;
  label?: string;
}): Promise<DeskOut> {
  const res = await fetch(`${API_BASE}/office/desks`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(desk),
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "desk creation failed");
  }
  return res.json();
}

export async function deleteDesk(deskId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/office/desks/${deskId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "desk deletion failed");
  }
}

export interface AgentStatusOut {
  agent_name: string;
  status: "active" | "idle";
  last_run: {
    id: string;
    agent_name: string;
    input: Record<string, unknown> | null;
    output: Record<string, unknown> | null;
    started_at: string;
    finished_at: string | null;
  } | null;
}

export function getAgentStatusWsUrl(): string {
  const base = `${API_BASE.replace(/^http/, "ws")}/agents/ws`;
  return sessionToken ? `${base}?token=${encodeURIComponent(sessionToken)}` : base;
}

export async function getAgentStatus(): Promise<AgentStatusOut[]> {
  const res = await fetch(`${API_BASE}/agents/status`, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "agent status fetch failed");
  }
  return res.json();
}

export interface DocumentSearchResult {
  document_id: string;
  content: string;
  similarity: number;
}

export async function createDocument(doc: {
  title: string;
  content: string;
  source_path?: string;
}): Promise<{ id: string; title: string | null; source_path: string | null }> {
  const res = await fetch(`${API_BASE}/documents`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(doc),
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "document creation failed");
  }
  return res.json();
}

export async function searchDocuments(q: string): Promise<DocumentSearchResult[]> {
  const res = await fetch(`${API_BASE}/documents/search?${new URLSearchParams({ q })}`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "document search failed");
  }
  return res.json();
}

export type AuditLogEntry =
  | {
      kind: "agent_run";
      timestamp: string;
      agent_name: string;
      finished_at: string | null;
      input: Record<string, unknown> | null;
      output: Record<string, unknown> | null;
    }
  | {
      kind: "approval";
      timestamp: string;
      target_type: string;
      status: string;
      thread_id: string;
    };

export async function getAuditLog(limit = 50): Promise<AuditLogEntry[]> {
  const res = await fetch(`${API_BASE}/audit/log?limit=${limit}`, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "audit log fetch failed");
  }
  return res.json();
}
