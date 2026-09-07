import { useEffect, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  getAuditLog,
  getFinanceSummary,
  getMarketingMetrics,
  listTasks,
  uploadReceipt,
  type AuditLogEntry,
  type FinanceSummaryPoint,
  type MarketingMetricOut,
  type TaskOut,
} from "../../lib/api";

const STATUS_COLOR: Record<string, string> = {
  todo: "#64748b",
  in_progress: "#886AFF",
  done: "#22c55e",
};

const STATUS_LABEL: Record<string, string> = {
  todo: "대기",
  in_progress: "진행중",
  done: "완료",
};

const CHANNEL_COLOR: Record<string, string> = {
  instagram: "#e1306c",
  facebook: "#1877f2",
  tiktok: "#69c9d0",
  threads: "#e4e4e4",
};

const APPROVAL_STATUS_STYLE: Record<string, string> = {
  pending: "bg-slate-700 text-slate-200",
  approved: "bg-green-900 text-green-300",
  rejected: "bg-red-900 text-red-300",
  revision: "bg-amber-900 text-amber-300",
};

export default function DashboardView() {
  const [tasks, setTasks] = useState<TaskOut[]>([]);
  const [summary, setSummary] = useState<FinanceSummaryPoint[]>([]);
  const [marketingMetrics, setMarketingMetrics] = useState<MarketingMetricOut[]>([]);
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = () => {
    setLoading(true);
    Promise.all([listTasks(), getFinanceSummary(), getMarketingMetrics(), getAuditLog()])
      .then(([taskData, summaryData, marketingData, auditData]) => {
        setTasks(taskData);
        setSummary(summaryData);
        setMarketingMetrics(marketingData);
        setAuditLog(auditData);
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

  const taskStatusData = Object.entries(
    tasks.reduce<Record<string, number>>((acc, t) => {
      acc[t.status] = (acc[t.status] ?? 0) + 1;
      return acc;
    }, {}),
  ).map(([status, count]) => ({ status, label: STATUS_LABEL[status] ?? status, count }));

  const channels = Array.from(new Set(marketingMetrics.map((m) => m.channel)));
  const metricsByDate = new Map<string, Record<string, number>>();
  for (const m of marketingMetrics) {
    const row = metricsByDate.get(m.metric_date) ?? {};
    row[m.channel] = (row[m.channel] ?? 0) + m.impressions;
    metricsByDate.set(m.metric_date, row);
  }
  const marketingChartData = Array.from(metricsByDate.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([metric_date, byChannel]) => ({ metric_date, ...byChannel }));

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
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
            <h2 className="mb-4 text-sm font-medium text-slate-300">업무 처리 현황</h2>
            {taskStatusData.length === 0 ? (
              <div className="text-sm text-slate-500">아직 등록된 Task가 없습니다.</div>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={taskStatusData}
                    dataKey="count"
                    nameKey="label"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={2}
                  >
                    {taskStatusData.map((entry) => (
                      <Cell key={entry.status} fill={STATUS_COLOR[entry.status] ?? "#64748b"} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
            <h2 className="mb-4 text-sm font-medium text-slate-300">현금 흐름 (승인된 지출, 월별)</h2>
            {summary.length === 0 ? (
              <div className="text-sm text-slate-500">승인된 회계 분개가 아직 없습니다.</div>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
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

          <div className="rounded-lg border border-slate-800 bg-slate-900 p-4 lg:col-span-2">
            <h2 className="mb-4 text-sm font-medium text-slate-300">채널별 마케팅 지표 추이 (노출수)</h2>
            {marketingChartData.length === 0 ? (
              <div className="text-sm text-slate-500">아직 게시된 마케팅 콘텐츠가 없습니다.</div>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={marketingChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="metric_date" stroke="#94a3b8" />
                  <YAxis stroke="#94a3b8" />
                  <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155" }} />
                  <Legend />
                  {channels.map((channel) => (
                    <Line
                      key={channel}
                      type="monotone"
                      dataKey={channel}
                      name={channel}
                      stroke={CHANNEL_COLOR[channel] ?? "#886AFF"}
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900 p-4 lg:col-span-2">
            <h2 className="mb-4 text-sm font-medium text-slate-300">감사 로그 (최근 활동)</h2>
            {auditLog.length === 0 ? (
              <div className="text-sm text-slate-500">아직 기록된 활동이 없습니다.</div>
            ) : (
              <div className="max-h-80 overflow-auto">
                <table className="w-full text-left text-xs">
                  <thead className="sticky top-0 bg-slate-900 text-slate-500">
                    <tr>
                      <th className="pb-2 pr-4 font-medium">시각</th>
                      <th className="pb-2 pr-4 font-medium">종류</th>
                      <th className="pb-2 pr-4 font-medium">내용</th>
                      <th className="pb-2 font-medium">상태</th>
                    </tr>
                  </thead>
                  <tbody className="text-slate-300">
                    {auditLog.map((entry, i) => (
                      <tr key={i} className="border-t border-slate-800">
                        <td className="py-2 pr-4 whitespace-nowrap text-slate-500">
                          {new Date(entry.timestamp).toLocaleString()}
                        </td>
                        <td className="py-2 pr-4 whitespace-nowrap">
                          {entry.kind === "agent_run" ? "에이전트 실행" : "승인 요청"}
                        </td>
                        <td className="py-2 pr-4">
                          {entry.kind === "agent_run" ? entry.agent_name : entry.target_type}
                        </td>
                        <td className="py-2">
                          {entry.kind === "agent_run" ? (
                            <span
                              className={`rounded px-2 py-0.5 ${
                                entry.finished_at
                                  ? "bg-slate-700 text-slate-300"
                                  : "bg-brand-purple/30 text-brand-purple"
                              }`}
                            >
                              {entry.finished_at ? "완료" : "진행중"}
                            </span>
                          ) : (
                            <span
                              className={`rounded px-2 py-0.5 ${
                                APPROVAL_STATUS_STYLE[entry.status] ?? "bg-slate-700 text-slate-300"
                              }`}
                            >
                              {entry.status}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
