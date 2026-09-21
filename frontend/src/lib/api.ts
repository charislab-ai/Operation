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

export async function submitRichDirective(text: string, files: File[]): Promise<DirectiveOut> {
  const formData = new FormData();
  formData.append("text", text);
  files.forEach((f) => formData.append("files", f));
  const res = await fetch(`${API_BASE}/directives`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "directive submission failed");
  }
  return res.json();
}

export async function updateDirective(threadId: string, ceoDirective: string): Promise<DirectiveOut> {
  const res = await fetch(`${API_BASE}/directives/${threadId}`, {
    method: "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ ceo_directive: ceoDirective }),
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "directive update failed");
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

export interface DirectiveListItem {
  thread_id: string;
  ceo_directive: string;
  created_at: string;
  latest_status: string;
}

export interface ApprovalRow {
  id: string;
  target_type: string;
  status: string;
  payload: Record<string, unknown> | null;
  created_at: string;
  awaiting_comment: boolean;
}

export interface AgentRunRow {
  id: string;
  agent_name: string;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  started_at: string;
  finished_at: string | null;
}

export interface AiUsageByAgent {
  agent_name: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  image_count: number;
  cost_usd: number | null;
}

export interface AiUsageSummary {
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_image_count: number;
  total_cost_usd: number | null;
  by_agent: AiUsageByAgent[];
}

export interface DirectiveDetail {
  thread_id: string;
  ceo_directive: string;
  created_at: string;
  status: string;
  active_departments: string[];
  worker_briefs: Record<string, string>;
  decisions: Record<string, string>;
  revision_notes: Record<string, string>;
  outputs: {
    biz_plan: Record<string, unknown> | null;
    wbs_plan: Record<string, unknown> | null;
    marketing_post: Record<string, unknown> | null;
    dev_proposal: Record<string, unknown> | null;
  };
  approvals: ApprovalRow[];
  agent_runs: AgentRunRow[];
  ai_usage: AiUsageSummary;
  media: DirectiveMediaOut[];
}

export interface DirectiveMediaOut {
  id: string;
  media_type: "image" | "video";
  url: string;
  caption: string | null;
}

export async function uploadDirectiveMedia(
  threadId: string,
  file: File,
  caption?: string,
): Promise<DirectiveMediaOut> {
  const formData = new FormData();
  formData.append("file", file);
  if (caption) formData.append("caption", caption);
  const res = await fetch(`${API_BASE}/directives/${threadId}/media`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "directive media upload failed");
  }
  return res.json();
}

export async function updateDirectiveMedia(
  threadId: string,
  mediaId: string,
  caption: string,
): Promise<DirectiveMediaOut> {
  const res = await fetch(`${API_BASE}/directives/${threadId}/media/${mediaId}`, {
    method: "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ caption }),
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "directive media update failed");
  }
  return res.json();
}

export async function deleteDirectiveMedia(threadId: string, mediaId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/directives/${threadId}/media/${mediaId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "directive media delete failed");
  }
}

export async function decideApproval(
  approvalId: string,
  decision: "approved" | "rejected" | "revision",
  comment?: string,
): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/approvals/${approvalId}/decide`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ decision, comment: comment ?? null }),
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "approval decision failed");
  }
  return res.json();
}

export async function pauseDirective(threadId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/directives/${threadId}/pause`, { method: "POST", headers: authHeaders() });
  if (!res.ok) throw new Error((await res.json()).detail ?? "directive pause failed");
}

export async function resumeDirective(threadId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/directives/${threadId}/resume`, { method: "POST", headers: authHeaders() });
  if (!res.ok) throw new Error((await res.json()).detail ?? "directive resume failed");
}

export async function terminateDirective(threadId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/directives/${threadId}/terminate`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? "directive terminate failed");
}

export async function deleteDirective(threadId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/directives/${threadId}`, { method: "DELETE", headers: authHeaders() });
  if (!res.ok) throw new Error((await res.json()).detail ?? "directive delete failed");
}

export async function listDirectives(): Promise<DirectiveListItem[]> {
  const res = await fetch(`${API_BASE}/directives`, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "directive list fetch failed");
  }
  return res.json();
}

export async function getDirectiveDetail(threadId: string): Promise<DirectiveDetail> {
  const res = await fetch(`${API_BASE}/directives/${threadId}/detail`, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "directive detail fetch failed");
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

export interface ProductAssetOut {
  id: string;
  product: string;
  description: string;
  url: string;
}

export async function listProductAssets(product?: string): Promise<ProductAssetOut[]> {
  const qs = product ? `?${new URLSearchParams({ product })}` : "";
  const res = await fetch(`${API_BASE}/marketing/assets${qs}`, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "product asset fetch failed");
  }
  return res.json();
}

export async function uploadProductAsset(
  product: string,
  description: string,
  file: File,
): Promise<ProductAssetOut> {
  const formData = new FormData();
  formData.append("product", product);
  formData.append("description", description);
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/marketing/assets`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "product asset upload failed");
  }
  return res.json();
}

export async function updateProductAsset(assetId: string, description: string): Promise<ProductAssetOut> {
  const res = await fetch(`${API_BASE}/marketing/assets/${assetId}`, {
    method: "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ description }),
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "product asset update failed");
  }
  return res.json();
}

export async function deleteProductAsset(assetId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/marketing/assets/${assetId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "product asset delete failed");
  }
}

export interface ProductOut {
  id: string;
  name: string;
  ios_url: string | null;
  android_url: string | null;
  brand_color: string | null;
  description: string | null;
  mascot_prompt: string | null;
  mascot_url: string | null;
}

export async function listProducts(): Promise<ProductOut[]> {
  const res = await fetch(`${API_BASE}/products`, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "product list fetch failed");
  }
  return res.json();
}

export async function createProduct(
  product: Pick<ProductOut, "name"> &
    Partial<Pick<ProductOut, "ios_url" | "android_url" | "brand_color" | "description">>,
): Promise<ProductOut> {
  const res = await fetch(`${API_BASE}/products`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(product),
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "product creation failed");
  }
  return res.json();
}

export async function updateProduct(
  name: string,
  patch: Partial<Pick<ProductOut, "ios_url" | "android_url" | "brand_color" | "description" | "mascot_prompt">>,
): Promise<ProductOut> {
  const res = await fetch(`${API_BASE}/products/${encodeURIComponent(name)}`, {
    method: "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "product update failed");
  }
  return res.json();
}

export async function regenerateMascot(name: string): Promise<ProductOut> {
  const res = await fetch(`${API_BASE}/products/${encodeURIComponent(name)}/mascot/regenerate`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "mascot regenerate failed");
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

export interface BenchmarkListItem {
  filename: string;
  date: string;
  time: string;
}

export interface BenchmarkDetail {
  filename: string;
  content: string;
}

export async function listBenchmarks(): Promise<BenchmarkListItem[]> {
  const res = await fetch(`${API_BASE}/marketing/benchmarks`, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "benchmark list fetch failed");
  }
  return res.json();
}

export async function getBenchmark(filename: string): Promise<BenchmarkDetail> {
  const res = await fetch(`${API_BASE}/marketing/benchmarks/${encodeURIComponent(filename)}`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail ?? "benchmark detail fetch failed");
  }
  return res.json();
}
