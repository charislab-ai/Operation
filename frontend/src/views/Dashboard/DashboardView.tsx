import { useEffect, useState } from "react";
import {
  getAuditLog,
  getMarketingMetrics,
  listDirectives,
  listProductAssets,
  listProducts,
  type AuditLogEntry,
  type DirectiveListItem,
  type MarketingMetricOut,
  type ProductAssetOut,
  type ProductOut,
} from "../../lib/api";
import type { ViewKey } from "../../components/Sidebar";

const STATUS_STYLE: Record<string, string> = {
  in_progress: "bg-blue-900 text-blue-300",
  pending_approval: "bg-slate-700 text-slate-200",
  approved: "bg-green-900 text-green-300",
  completed: "bg-slate-700 text-slate-200",
  rejected: "bg-red-900 text-red-300",
  failed: "bg-red-900 text-red-300",
  paused: "bg-amber-900 text-amber-300",
  terminated: "bg-red-950 text-red-400",
};

const STATUS_LABEL: Record<string, string> = {
  in_progress: "진행중",
  pending_approval: "승인 대기",
  approved: "승인됨",
  completed: "완료",
  rejected: "반려됨",
  failed: "실패",
  paused: "정지됨",
  terminated: "강제 종료됨",
};

function StatCard({
  label,
  value,
  detail,
  tone,
  onClick,
}: {
  label: string;
  value: string;
  detail: string;
  tone?: "alert";
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-lg border p-4 text-left transition hover:border-slate-600 ${
        tone === "alert" ? "border-red-900 bg-red-950/30" : "border-slate-800 bg-slate-900"
      }`}
    >
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-100">{value}</div>
      <div className="mt-1 text-xs text-slate-400">{detail}</div>
    </button>
  );
}

export default function DashboardView({ onNavigate }: { onNavigate: (key: ViewKey) => void }) {
  const [directives, setDirectives] = useState<DirectiveListItem[]>([]);
  const [metrics, setMetrics] = useState<MarketingMetricOut[]>([]);
  const [assets, setAssets] = useState<ProductAssetOut[]>([]);
  const [products, setProducts] = useState<ProductOut[]>([]);
  const [audit, setAudit] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listDirectives(), getMarketingMetrics(), listProductAssets(), listProducts(), getAuditLog(20)])
      .then(([d, m, a, p, l]) => {
        setDirectives(d);
        setMetrics(m);
        setAssets(a);
        setProducts(p);
        setAudit(l);
        setError(null);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  const needsAttention = directives.filter((d) => d.latest_status === "pending_approval").length;
  const running = directives.filter((d) => d.latest_status === "in_progress").length;
  const failed = directives.filter((d) => d.latest_status === "failed").length;
  const published = metrics.length;

  return (
    <div className="flex h-full flex-col gap-6 overflow-auto p-6 text-slate-100">
      <h1 className="text-lg font-semibold">Dashboard</h1>
      {error && <div className="text-sm text-red-400">{error}</div>}

      {loading ? (
        <div className="text-slate-400">불러오는 중...</div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="내 결재 대기"
              value={`${needsAttention}건`}
              detail={needsAttention > 0 ? "확인이 필요합니다" : "대기중인 결재 없음"}
              onClick={() => onNavigate("workOrders")}
            />
            <StatCard
              label="진행중인 업무"
              value={`${running}건`}
              detail="AI가 작업 중"
              onClick={() => onNavigate("workOrders")}
            />
            <StatCard
              label="실패한 업무"
              value={`${failed}건`}
              detail={failed > 0 ? "원인 확인 필요" : "정상"}
              tone={failed > 0 ? "alert" : undefined}
              onClick={() => onNavigate("workOrders")}
            />
            <StatCard
              label="게시 완료"
              value={`${published}건`}
              detail={`앱 ${products.length}개 · 스크린샷 ${assets.length}장`}
              onClick={() => onNavigate("appManagement")}
            />
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
            <h2 className="mb-3 text-sm font-medium text-slate-300">최근 업무 지시</h2>
            {directives.length === 0 ? (
              <div className="text-sm text-slate-500">아직 지시가 없습니다.</div>
            ) : (
              <div className="flex flex-col gap-2">
                {directives.slice(0, 6).map((d) => (
                  <button
                    key={d.thread_id}
                    onClick={() => onNavigate("workOrders")}
                    className="flex items-center gap-3 rounded-md border border-slate-800 px-3 py-2 text-left hover:bg-slate-800/50"
                  >
                    <span
                      className={`shrink-0 rounded px-2 py-0.5 text-xs ${
                        STATUS_STYLE[d.latest_status] ?? "bg-slate-700 text-slate-200"
                      }`}
                    >
                      {STATUS_LABEL[d.latest_status] ?? d.latest_status}
                    </span>
                    <span className="truncate text-sm text-slate-300">{d.ceo_directive}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
            <h2 className="mb-3 text-sm font-medium text-slate-300">게시된 콘텐츠</h2>
            {metrics.length === 0 ? (
              <div className="text-sm text-slate-500">아직 게시된 콘텐츠가 없습니다.</div>
            ) : (
              <table className="w-full text-left text-xs">
                <thead className="text-slate-500">
                  <tr>
                    <th className="pb-2 pr-4 font-medium">일자</th>
                    <th className="pb-2 pr-4 font-medium">앱</th>
                    <th className="pb-2 pr-4 font-medium">채널</th>
                    <th className="pb-2 font-medium">게시물</th>
                  </tr>
                </thead>
                <tbody className="text-slate-300">
                  {metrics.map((m, i) => (
                    <tr key={i} className="border-t border-slate-800">
                      <td className="py-2 pr-4 whitespace-nowrap">{m.metric_date}</td>
                      <td className="py-2 pr-4">{m.product}</td>
                      <td className="py-2 pr-4">{m.channel}</td>
                      <td className="py-2">
                        {m.permalink ? (
                          <a href={m.permalink} target="_blank" rel="noreferrer" className="text-brand-purple hover:underline">
                            게시물 보기 ↗
                          </a>
                        ) : (
                          <span className="text-slate-500">{m.post_id ?? "-"}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
            <h2 className="mb-3 text-sm font-medium text-slate-300">최근 활동</h2>
            {audit.length === 0 ? (
              <div className="text-sm text-slate-500">기록 없음</div>
            ) : (
              <ul className="flex flex-col gap-1 text-xs text-slate-400">
                {audit.slice(0, 10).map((a, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="shrink-0 text-slate-600">
                      {new Date(a.timestamp).toLocaleString("ko-KR")}
                    </span>
                    <span className="truncate">
                      {a.kind === "agent_run" ? `${a.agent_name} 실행` : `결재 ${a.status ?? ""}`}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
