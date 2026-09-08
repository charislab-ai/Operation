import { useEffect, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  getAuditLog,
  getFinanceSummary,
  getMarketingMetrics,
  listDirectives,
  listProductAssets,
  listTasks,
  uploadReceipt,
  type AuditLogEntry,
  type DirectiveListItem,
  type FinanceSummaryPoint,
  type MarketingMetricOut,
  type ProductAssetOut,
  type TaskOut,
} from "../../lib/api";
import type { ViewKey } from "../../components/Sidebar";

const STATUS_LABEL: Record<string, string> = {
  todo: "대기",
  in_progress: "진행중",
  done: "완료",
};

const APPROVAL_STATUS_STYLE: Record<string, string> = {
  pending: "bg-slate-700 text-slate-200",
  approved: "bg-green-900 text-green-300",
  rejected: "bg-red-900 text-red-300",
  revision: "bg-amber-900 text-amber-300",
};

function StatCard({
  label,
  value,
  detail,
  onClick,
}: {
  label: string;
  value: string;
  detail?: string;
  onClick?: () => void;
}) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      onClick={onClick}
      className={`rounded-lg border border-slate-800 bg-slate-900 p-4 text-left ${
        onClick ? "hover:border-brand-purple" : ""
      }`}
    >
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-100">{value}</div>
      {detail && <div className="mt-1 text-xs text-slate-500">{detail}</div>}
    </Tag>
  );
}

export default function DashboardView({ onNavigate }: { onNavigate: (key: ViewKey) => void }) {
  const [tasks, setTasks] = useState<TaskOut[]>([]);
  const [summary, setSummary] = useState<FinanceSummaryPoint[]>([]);
  const [marketingMetrics, setMarketingMetrics] = useState<MarketingMetricOut[]>([]);
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([]);
  const [directives, setDirectives] = useState<DirectiveListItem[]>([]);
  const [assets, setAssets] = useState<ProductAssetOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = () => {
    setLoading(true);
    Promise.all([
      listTasks(),
      getFinanceSummary(),
      getMarketingMetrics(),
      getAuditLog(),
      listDirectives(),
      listProductAssets(),
    ])
      .then(([taskData, summaryData, marketingData, auditData, directiveData, assetData]) => {
        setTasks(taskData);
        setSummary(summaryData);
        setMarketingMetrics(marketingData);
        setAuditLog(auditData);
        setDirectives(directiveData);
        setAssets(assetData);
        setError(null);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadMessage(null);
    try {
      await uploadReceipt(file);
      setUploadMessage("영수증 분석 완료 — 텔레그램으로 승인 요청을 보냈습니다.");
    } catch (err) {
      setUploadMessage(`업로드 실패: ${(err as Error).message}`);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const taskCounts = tasks.reduce<Record<string, number>>((acc, t) => {
    acc[t.status] = (acc[t.status] ?? 0) + 1;
    return acc;
  }, {});
  const pendingDirectives = directives.filter((d) => d.latest_status === "pending").length;
  const totalImpressions = marketingMetrics.reduce((sum, m) => sum + m.impressions, 0);
  const recentActivity = auditLog.slice(0, 5);

  return (
    <div className="flex h-full flex-col gap-6 overflow-auto p-6 text-slate-100">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Dashboard</h1>
        <div className="flex items-center gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleFileSelected}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="rounded-md bg-brand-purple px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            {uploading ? "분석중..." : "영수증 업로드"}
          </button>
          <button
            onClick={load}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
          >
            새로고침
          </button>
        </div>
      </div>

      {uploadMessage && <div className="text-sm text-slate-300">{uploadMessage}</div>}
      {error && <div className="text-sm text-red-400">{error}</div>}

      {loading ? (
        <div className="text-slate-400">불러오는 중...</div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="업무 지시"
              value={`${directives.length}건`}
              detail={pendingDirectives > 0 ? `승인 대기 ${pendingDirectives}건` : "대기중인 승인 없음"}
              onClick={() => onNavigate("workOrders")}
            />
            <StatCard
              label="일정 / Task"
              value={`${tasks.length}건`}
              detail={`대기 ${taskCounts.todo ?? 0} · 진행중 ${taskCounts.in_progress ?? 0} · 완료 ${taskCounts.done ?? 0}`}
              onClick={() => onNavigate("calendar")}
            />
            <StatCard
              label="마케팅 노출수 합계"
              value={totalImpressions.toLocaleString()}
              detail={`${marketingMetrics.length}건 게시`}
              onClick={() => onNavigate("workOrders")}
            />
            <StatCard
              label="등록된 앱 스크린샷"
              value={`${assets.length}장`}
              detail="앱관리에서 관리"
              onClick={() => onNavigate("appManagement")}
            />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
              <h2 className="mb-4 text-sm font-medium text-slate-300">현금 흐름 (승인된 지출, 월별)</h2>
              {summary.length === 0 ? (
                <div className="text-sm text-slate-500">승인된 회계 분개가 아직 없습니다.</div>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={summary}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="period" stroke="#94a3b8" />
                    <YAxis stroke="#94a3b8" />
                    <Tooltip
                      formatter={(value) => `${Number(value).toLocaleString()}원`}
                      contentStyle={{ background: "#1e293b", border: "1px solid #334155" }}
                    />
                    <Bar dataKey="expense" name="지출" fill="#886AFF" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            <button
              onClick={() => onNavigate("workOrders")}
              className="rounded-lg border border-slate-800 bg-slate-900 p-4 text-left hover:border-brand-purple"
            >
              <h2 className="mb-4 text-sm font-medium text-slate-300">최근 활동 (자세히 보기 →)</h2>
              {recentActivity.length === 0 ? (
                <div className="text-sm text-slate-500">아직 기록된 활동이 없습니다.</div>
              ) : (
                <div className="flex flex-col gap-2">
                  {recentActivity.map((entry, i) => (
                    <div key={i} className="flex items-center justify-between text-xs">
                      <span className="text-slate-500">{new Date(entry.timestamp).toLocaleString()}</span>
                      <span className="truncate px-2 text-slate-300">
                        {entry.kind === "agent_run" ? entry.agent_name : entry.target_type}
                      </span>
                      {entry.kind === "agent_run" ? (
                        <span
                          className={`rounded px-2 py-0.5 ${
                            entry.finished_at ? "bg-slate-700 text-slate-300" : "bg-brand-purple/30 text-brand-purple"
                          }`}
                        >
                          {entry.finished_at ? "완료" : "진행중"}
                        </span>
                      ) : (
                        <span className={`rounded px-2 py-0.5 ${APPROVAL_STATUS_STYLE[entry.status] ?? "bg-slate-700 text-slate-300"}`}>
                          {STATUS_LABEL[entry.status] ?? entry.status}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
