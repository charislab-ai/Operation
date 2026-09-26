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
  last_error: string | null;
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











export interface MarketingMetricOut {
  permalink?: string | null;
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
  tone_of_voice?: string | null;
  target_audience?: string | null;
  key_messages?: string | null;
  banned_words?: string | null;
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
  patch: Partial<
    Pick<
      ProductOut,
      | "ios_url"
      | "android_url"
      | "brand_color"
      | "description"
      | "mascot_prompt"
      | "tone_of_voice"
      | "target_audience"
      | "key_messages"
      | "banned_words"
    >
  >,
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

export interface AutoScheduleOut {
  enabled: boolean;
  interval_hours: number;
  products: string[];
  last_run_at: string | null;
  last_product: string | null;
}

export async function getAutoSchedule(): Promise<AutoScheduleOut> {
  const res = await fetch(`${API_BASE}/marketing/auto-schedule`, { headers: authHeaders() });
  if (!res.ok) throw new Error((await res.json()).detail ?? "auto schedule fetch failed");
  return res.json();
}

export async function updateAutoSchedule(
  patch: Partial<Pick<AutoScheduleOut, "enabled" | "interval_hours" | "products">>,
): Promise<AutoScheduleOut> {
  const res = await fetch(`${API_BASE}/marketing/auto-schedule`, {
    method: "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? "auto schedule update failed");
  return res.json();
}

export interface AiBudgetOut {
  enabled: boolean;
  daily_image_limit: number;
  daily_token_limit: number;
  per_thread_image_limit: number;
  used_images_today: number;
  used_tokens_today: number;
}

export async function getAiBudget(): Promise<AiBudgetOut> {
  const res = await fetch(`${API_BASE}/marketing/ai-budget`, { headers: authHeaders() });
  if (!res.ok) throw new Error((await res.json()).detail ?? "ai budget fetch failed");
  return res.json();
}

export async function updateAiBudget(
  patch: Partial<Pick<AiBudgetOut, "enabled" | "daily_image_limit" | "daily_token_limit" | "per_thread_image_limit">>,
): Promise<AiBudgetOut> {
  const res = await fetch(`${API_BASE}/marketing/ai-budget`, {
    method: "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? "ai budget update failed");
  return res.json();
}

export interface LayoutOut {
  id: string;
  name: string;
  when_to_use: string;
  spec: Record<string, unknown>;
  source: string | null;
  enabled: boolean;
  times_used: number;
}

export async function listLayouts(): Promise<LayoutOut[]> {
  const res = await fetch(`${API_BASE}/marketing/layouts`, { headers: authHeaders() });
  if (!res.ok) throw new Error((await res.json()).detail ?? "layout list failed");
  return res.json();
}

export async function toggleLayout(layoutId: string, enabled: boolean): Promise<LayoutOut> {
  const res = await fetch(`${API_BASE}/marketing/layouts/${layoutId}?enabled=${enabled}`, {
    method: "PATCH",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? "layout toggle failed");
  return res.json();
}

// ── 슬라이드 편집기 ──────────────────────────────────────────────────────────
// 승인 전에 카드의 문구/틀을 고쳐 바로 다시 그려본다. 미리보기(render-preview)는 AI를
// 호출하지 않아 비용이 0이고, 사진 재생성(regenerate-photo)만 유료다.

export interface SlideEdit {
  headline: string;
  subtext: string;
  layout_name?: string;
  layout_spec?: Record<string, unknown>;
  source_image_url?: string | null;
  image_prompt?: string;
}

export async function renderSlidePreview(input: {
  product: string;
  format?: string;
  page_label?: string | null;
  headline: string;
  subtext: string;
  layout_spec?: Record<string, unknown>;
  source_image_url?: string | null;
}): Promise<string> {
  const res = await fetch(`${API_BASE}/marketing/render-preview`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? "preview failed");
  return (await res.json()).image_data_url as string;
}

export async function saveMarketingPost(
  approvalId: string,
  body: { caption?: string; slides: SlideEdit[] },
): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/marketing/posts/${approvalId}`, {
    method: "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? "save failed");
  return res.json();
}

export async function regenerateSlidePhoto(imagePrompt: string, threadId?: string): Promise<string> {
  const res = await fetch(`${API_BASE}/marketing/regenerate-photo`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ image_prompt: imagePrompt, thread_id: threadId }),
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? "regenerate failed");
  return (await res.json()).source_image_url as string;
}

// ── 직원 명단 ────────────────────────────────────────────────────────────────
// 각 AI 에이전트는 직원으로 등록돼 있고, CEO가 이름을 지어줄 수 있다. 지시문에서 그 이름을
// 부르면 해당 직원만 자기 지시로 받아들인다(백엔드 supervisor / addressing_note).

export interface EmployeeOut {
  id: string;
  agent_key: string;
  name: string;
  title: string;
  rank: string;
  department: string;
  responsibilities: string;
  status: "active" | "onboarding" | "leave";
  sort_order: number;
  working: boolean;
  current_task: string | null;
  last_active_at: string | null;
  runs_7d: number;
  tokens_7d: number;
  hire_readiness: {
    checks: { label: string; current: number; raw: number; needed: number; unit: string; met: boolean }[];
    ready: boolean;
    why: string;
    progress: number;
  } | null;
  hire_recommended_at: string | null;
}

export async function listEmployees(): Promise<EmployeeOut[]> {
  const res = await fetch(`${API_BASE}/employees`, { headers: authHeaders() });
  if (!res.ok) throw new Error((await res.json()).detail ?? "employee list failed");
  return res.json();
}

export async function updateEmployee(
  agentKey: string,
  patch: Partial<Pick<EmployeeOut, "name" | "title" | "rank" | "responsibilities" | "status">>,
): Promise<EmployeeOut> {
  const res = await fetch(`${API_BASE}/employees/${agentKey}`, {
    method: "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? "employee update failed");
  return res.json();
}

// ── 쇼츠/릴스 ────────────────────────────────────────────────────────────────
// 이미 만든 이미지를 재활용해 세로 영상을 만든다(AI 비용 0). 앱 화면 녹화를 올려
// 브랜드 헤더·자막·CTA를 얹은 쇼츠로 만드는 경로도 있다.

export async function regenerateShorts(approvalId: string): Promise<string> {
  const res = await fetch(`${API_BASE}/marketing/posts/${approvalId}/shorts`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? "shorts failed");
  return (await res.json()).video_url as string;
}

export async function screenRecordingToShorts(
  product: string,
  file: File,
  subtitle = "",
  seconds = 20,
): Promise<string> {
  const form = new FormData();
  form.append("product", product);
  form.append("subtitle", subtitle);
  form.append("seconds", String(seconds));
  form.append("file", file);
  const res = await fetch(`${API_BASE}/marketing/screen-recording`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? "screen recording failed");
  return (await res.json()).video_url as string;
}

// ── 게시 자료실 ──────────────────────────────────────────────────────────────
// 만들어진 콘텐츠(문구/태그/이미지/영상)를 모아서 보고 내려받는다. 릴스는 CEO가 인스타 앱에서
// 직접 올리며 음악을 고르기로 해서, 완성된 파일을 손에 넣을 수 있어야 한다.

export interface LibraryItem {
  approval_id: string;
  thread_id: string;
  product: string | null;
  channel: string | null;
  format: string | null;
  status: string;
  created_at: string;
  caption: string | null;
  hashtags: string[];
  image_urls: string[];
  video_url: string | null;
  permalink: string | null;
  director_notes: string | null;
  qa_summary: string | null;
}

export async function listLibrary(limit = 50): Promise<LibraryItem[]> {
  const res = await fetch(`${API_BASE}/marketing/library?limit=${limit}`, { headers: authHeaders() });
  if (!res.ok) throw new Error((await res.json()).detail ?? "library load failed");
  return res.json();
}

/** zip(이미지+영상+문구) 내려받기 - 인증 헤더가 필요해 fetch 후 blob으로 저장한다. */
export async function downloadBundle(item: LibraryItem): Promise<void> {
  const res = await fetch(`${API_BASE}/marketing/library/${item.approval_id}/bundle`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("다운로드 실패");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${item.product ?? "post"}_${item.created_at.slice(0, 10)}.zip`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
