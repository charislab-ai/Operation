import { useEffect, useState } from "react";
import {
  getDirectiveDetail,
  listDirectives,
  type AgentRunRow,
  type ApprovalRow,
  type DirectiveDetail,
  type DirectiveListItem,
} from "../../lib/api";

const STATUS_STYLE: Record<string, string> = {
  pending: "bg-slate-700 text-slate-200",
  approved: "bg-green-900 text-green-300",
  rejected: "bg-red-900 text-red-300",
  revision: "bg-amber-900 text-amber-300",
  completed: "bg-slate-700 text-slate-200",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "승인 대기",
  approved: "승인됨",
  rejected: "반려됨",
  revision: "보완 요청",
  completed: "완료",
};

const DEPT_LABEL: Record<string, string> = {
  bizdev: "사업개발",
  pm: "PM",
  marketing: "마케팅",
  dev: "개발",
};

type TimelineEvent =
  | { kind: "agent_run"; timestamp: string; row: AgentRunRow }
  | { kind: "approval"; timestamp: string; row: ApprovalRow };

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ko-KR");
  } catch {
    return iso;
  }
}

function StatusPill({ status }: { status: string }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs ${STATUS_STYLE[status] ?? "bg-slate-700 text-slate-200"}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

function CostCell({ value }: { value: number | null }) {
  if (value === null) return <span className="text-slate-500">정보 없음</span>;
  return <span>${value.toFixed(4)}</span>;
}

export default function WorkOrdersView() {
  const [directives, setDirectives] = useState<DirectiveListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<DirectiveDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    listDirectives()
      .then((data) => {
        setDirectives(data);
        setError(null);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const loadDetail = (threadId: string) => {
    setSelected(threadId);
    setDetailLoading(true);
    setDetailError(null);
    getDirectiveDetail(threadId)
      .then(setDetail)
      .catch((e) => setDetailError((e as Error).message))
      .finally(() => setDetailLoading(false));
  };

  if (selected) {
    const timeline: TimelineEvent[] = detail
      ? [
          ...detail.agent_runs.map((row): TimelineEvent => ({ kind: "agent_run", timestamp: row.started_at, row })),
          ...detail.approvals.map((row): TimelineEvent => ({ kind: "approval", timestamp: row.created_at, row })),
        ].sort((a, b) => a.timestamp.localeCompare(b.timestamp))
      : [];
    const inProgress = detail?.agent_runs.find((r) => !r.finished_at);
    const outputs = detail?.outputs;

    return (
      <div className="flex h-full flex-col gap-6 overflow-auto p-6 text-slate-100">
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setSelected(null);
              setDetail(null);
            }}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
          >
            ← 목록으로
          </button>
          <button
            onClick={() => loadDetail(selected)}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
          >
            새로고침
          </button>
          <span className="text-xs text-slate-500">{selected}</span>
        </div>

        {detailError && <div className="text-sm text-red-400">{detailError}</div>}

        {detailLoading || !detail ? (
          <div className="text-slate-400">불러오는 중...</div>
        ) : (
          <div className="flex flex-col gap-6">
            <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
              <h2 className="mb-3 text-sm font-medium text-slate-300">개요</h2>
              <div className="mb-3 flex flex-wrap gap-2">
                {detail.active_departments.length === 0 ? (
                  <span className="text-sm text-slate-500">배정된 부서 없음</span>
                ) : (
                  detail.active_departments.map((d) => (
                    <span key={d} className="rounded bg-brand-purple/20 px-2 py-0.5 text-xs text-brand-purple">
                      {DEPT_LABEL[d] ?? d}
                    </span>
                  ))
                )}
              </div>
              <div className="whitespace-pre-wrap text-sm text-slate-100">{detail.ceo_directive}</div>
              <div className="mt-2 text-xs text-slate-500">{formatDate(detail.created_at)} 제출</div>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
              <h2 className="mb-3 text-sm font-medium text-slate-300">부서별 진행상황 / 타임라인</h2>
              <div className="mb-3 text-sm">
                {inProgress ? (
                  <span className="text-brand-purple">현재 작업중: {inProgress.agent_name}</span>
                ) : (
                  <span className="text-slate-500">현재 진행 중인 작업 없음</span>
                )}
              </div>
              {timeline.length === 0 ? (
                <div className="text-sm text-slate-500">아직 기록된 활동이 없습니다.</div>
              ) : (
                <div className="max-h-80 overflow-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="sticky top-0 bg-slate-900 text-slate-500">
                      <tr>
                        <th className="pb-2 pr-4 font-medium">시각</th>
                        <th className="pb-2 pr-4 font-medium">구분</th>
                        <th className="pb-2 pr-4 font-medium">에이전트/부서</th>
                        <th className="pb-2 font-medium">상태</th>
                      </tr>
                    </thead>
                    <tbody className="text-slate-300">
                      {timeline.map((ev, i) => (
                        <tr key={i} className="border-t border-slate-800">
                          <td className="py-2 pr-4 whitespace-nowrap text-slate-500">{formatDate(ev.timestamp)}</td>
                          <td className="py-2 pr-4 whitespace-nowrap">
                            {ev.kind === "agent_run" ? "실행" : "승인"}
                          </td>
                          <td className="py-2 pr-4">
                            {ev.kind === "agent_run" ? ev.row.agent_name : DEPT_LABEL[ev.row.target_type] ?? ev.row.target_type}
                          </td>
                          <td className="py-2">
                            {ev.kind === "agent_run" ? (
                              <span
                                className={`rounded px-2 py-0.5 ${
                                  ev.row.finished_at ? "bg-slate-700 text-slate-300" : "bg-brand-purple/30 text-brand-purple"
                                }`}
                              >
                                {ev.row.finished_at ? "완료" : "진행중"}
                              </span>
                            ) : (
                              <StatusPill status={ev.row.status} />
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
              <h2 className="mb-3 text-sm font-medium text-slate-300">산출물</h2>
              {!outputs?.biz_plan && !outputs?.wbs_plan && !outputs?.marketing_post && !outputs?.dev_proposal ? (
                <div className="text-sm text-slate-500">아직 생성된 산출물이 없습니다.</div>
              ) : (
                <div className="flex flex-col gap-4">
                  {outputs?.biz_plan && (
                    <div className="rounded-md border border-slate-800 p-3 text-sm">
                      <div className="mb-2 font-medium text-slate-200">사업 기획서</div>
                      <div className="grid grid-cols-1 gap-1 text-slate-300 sm:grid-cols-2">
                        <div><span className="text-slate-500">문제: </span>{String(outputs.biz_plan.problem ?? "")}</div>
                        <div><span className="text-slate-500">타겟 시장: </span>{String(outputs.biz_plan.target_market ?? "")}</div>
                        <div><span className="text-slate-500">MVP 범위: </span>{String(outputs.biz_plan.mvp_scope ?? "")}</div>
                        <div><span className="text-slate-500">리스크: </span>{String(outputs.biz_plan.risks ?? "")}</div>
                        <div className="sm:col-span-2"><span className="text-slate-500">다음 액션: </span>{String(outputs.biz_plan.recommended_next_action ?? "")}</div>
                      </div>
                    </div>
                  )}

                  {outputs?.wbs_plan && (
                    <div className="rounded-md border border-slate-800 p-3 text-sm">
                      <div className="mb-2 font-medium text-slate-200">
                        WBS: {String(outputs.wbs_plan.project_title ?? "")}
                      </div>
                      <table className="w-full text-left text-xs">
                        <thead className="text-slate-500">
                          <tr>
                            <th className="pb-1 pr-3 font-medium">작업</th>
                            <th className="pb-1 pr-3 font-medium">부서</th>
                            <th className="pb-1 pr-3 font-medium">담당</th>
                            <th className="pb-1 font-medium">기간</th>
                          </tr>
                        </thead>
                        <tbody className="text-slate-300">
                          {((outputs.wbs_plan.tasks as Array<Record<string, unknown>>) ?? []).map((t, i) => (
                            <tr key={i} className="border-t border-slate-800">
                              <td className="py-1 pr-3">{String(t.title ?? "")}</td>
                              <td className="py-1 pr-3">{String(t.dept ?? "")}</td>
                              <td className="py-1 pr-3">{String(t.assignee_agent ?? "")}</td>
                              <td className="py-1 whitespace-nowrap">
                                {String(t.start_date ?? "")} ~ {String(t.end_date ?? "")}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {outputs?.marketing_post && (
                    <div className="rounded-md border border-slate-800 p-3 text-sm">
                      <div className="mb-2 flex items-center gap-2 font-medium text-slate-200">
                        마케팅 카드뉴스
                        <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                          {String(outputs.marketing_post.product ?? "")}
                        </span>
                        <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                          {String(outputs.marketing_post.channel ?? "")}
                        </span>
                      </div>
                      <div className="mb-2 whitespace-pre-wrap text-slate-300">
                        {String(outputs.marketing_post.caption ?? "")}
                      </div>
                      {Array.isArray(outputs.marketing_post.image_urls) && outputs.marketing_post.image_urls.length > 0 && (
                        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
                          {(outputs.marketing_post.image_urls as string[]).map((url, i) => (
                            <img key={i} src={url} alt={`slide ${i + 1}`} className="aspect-square w-full rounded object-cover" />
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {outputs?.dev_proposal && (
                    <div className="rounded-md border border-slate-800 p-3 text-sm">
                      <div className="mb-2 font-medium text-slate-200">{String(outputs.dev_proposal.title ?? "")}</div>
                      <div className="mb-2 text-slate-300">{String(outputs.dev_proposal.summary ?? "")}</div>
                      {Array.isArray(outputs.dev_proposal.files_affected) && (
                        <ul className="mb-2 list-disc pl-5 text-xs text-slate-400">
                          {(outputs.dev_proposal.files_affected as string[]).map((f, i) => (
                            <li key={i}>{f}</li>
                          ))}
                        </ul>
                      )}
                      {typeof outputs.dev_proposal.code_sketch === "string" && (
                        <pre className="mb-2 overflow-auto rounded bg-slate-950 p-2 text-xs text-slate-300">
                          {outputs.dev_proposal.code_sketch}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
              <h2 className="mb-3 text-sm font-medium text-slate-300">결정사항</h2>
              {detail.approvals.length === 0 ? (
                <div className="text-sm text-slate-500">아직 승인 요청이 없습니다.</div>
              ) : (
                <table className="w-full text-left text-xs">
                  <thead className="text-slate-500">
                    <tr>
                      <th className="pb-2 pr-4 font-medium">부서</th>
                      <th className="pb-2 pr-4 font-medium">상태</th>
                      <th className="pb-2 pr-4 font-medium">시각</th>
                      <th className="pb-2 font-medium">보완 사유</th>
                    </tr>
                  </thead>
                  <tbody className="text-slate-300">
                    {detail.approvals.map((a) => (
                      <tr key={a.id} className="border-t border-slate-800">
                        <td className="py-2 pr-4">{DEPT_LABEL[a.target_type] ?? a.target_type}</td>
                        <td className="py-2 pr-4"><StatusPill status={a.status} /></td>
                        <td className="py-2 pr-4 whitespace-nowrap text-slate-500">{formatDate(a.created_at)}</td>
                        <td className="py-2">{detail.revision_notes[a.target_type] ?? "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
              <h2 className="mb-3 text-sm font-medium text-slate-300">AI 사용량</h2>
              {detail.ai_usage.by_agent.length === 0 ? (
                <div className="text-sm text-slate-500">기록된 AI 사용량이 없습니다.</div>
              ) : (
                <table className="w-full text-left text-xs">
                  <thead className="text-slate-500">
                    <tr>
                      <th className="pb-2 pr-4 font-medium">에이전트</th>
                      <th className="pb-2 pr-4 font-medium">입력 토큰</th>
                      <th className="pb-2 pr-4 font-medium">출력 토큰</th>
                      <th className="pb-2 pr-4 font-medium">합계 토큰</th>
                      <th className="pb-2 pr-4 font-medium">이미지 수</th>
                      <th className="pb-2 font-medium">비용</th>
                    </tr>
                  </thead>
                  <tbody className="text-slate-300">
                    {detail.ai_usage.by_agent.map((b) => (
                      <tr key={b.agent_name} className="border-t border-slate-800">
                        <td className="py-2 pr-4">{b.agent_name}</td>
                        <td className="py-2 pr-4 tabular-nums">{b.input_tokens.toLocaleString()}</td>
                        <td className="py-2 pr-4 tabular-nums">{b.output_tokens.toLocaleString()}</td>
                        <td className="py-2 pr-4 tabular-nums">{b.total_tokens.toLocaleString()}</td>
                        <td className="py-2 pr-4 tabular-nums">{b.image_count}</td>
                        <td className="py-2"><CostCell value={b.cost_usd} /></td>
                      </tr>
                    ))}
                    <tr className="border-t border-slate-700 font-medium text-slate-100">
                      <td className="py-2 pr-4">합계</td>
                      <td className="py-2 pr-4 tabular-nums">{detail.ai_usage.total_input_tokens.toLocaleString()}</td>
                      <td className="py-2 pr-4 tabular-nums">{detail.ai_usage.total_output_tokens.toLocaleString()}</td>
                      <td className="py-2 pr-4 tabular-nums">{detail.ai_usage.total_tokens.toLocaleString()}</td>
                      <td className="py-2 pr-4 tabular-nums">{detail.ai_usage.total_image_count}</td>
                      <td className="py-2"><CostCell value={detail.ai_usage.total_cost_usd} /></td>
                    </tr>
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-6 overflow-auto p-6 text-slate-100">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">업무 지시</h1>
        <button
          onClick={load}
          className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
        >
          새로고침
        </button>
      </div>

      {error && <div className="text-sm text-red-400">{error}</div>}

      {loading ? (
        <div className="text-slate-400">불러오는 중...</div>
      ) : directives.length === 0 ? (
        <div className="text-sm text-slate-500">아직 등록된 지시가 없습니다.</div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {directives.map((d) => (
            <button
              key={d.thread_id}
              onClick={() => loadDetail(d.thread_id)}
              className="rounded-lg border border-slate-800 bg-slate-900 p-4 text-left hover:border-brand-purple"
            >
              <div className="mb-2 flex items-center justify-between">
                <StatusPill status={d.latest_status} />
                <span className="text-xs text-slate-500">{formatDate(d.created_at)}</span>
              </div>
              <div className="line-clamp-3 text-sm text-slate-100">{d.ceo_directive}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
