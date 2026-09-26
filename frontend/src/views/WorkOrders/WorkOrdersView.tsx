import { useEffect, useRef, useState } from "react";
import PostPreviewModal from "../../components/PostPreviewModal";
import {
  decideApproval,
  deleteDirective,
  deleteDirectiveMedia,
  getDirectiveDetail,
  getAiBudget,
  getAutoSchedule,
  listDirectives,
  pauseDirective,
  resumeDirective,
  terminateDirective,
  updateDirective,
  updateAiBudget,
  updateAutoSchedule,
  updateDirectiveMedia,
  uploadDirectiveMedia,
  type AgentRunRow,
  type ApprovalRow,
  type DirectiveDetail,
  type AiBudgetOut,
  type AutoScheduleOut,
  type DirectiveListItem,
} from "../../lib/api";

const STATUS_STYLE: Record<string, string> = {
  pending: "bg-slate-700 text-slate-200",
  pending_approval: "bg-slate-700 text-slate-200",
  processing: "bg-blue-900 text-blue-300",
  in_progress: "bg-blue-900 text-blue-300",
  approved: "bg-green-900 text-green-300",
  rejected: "bg-red-900 text-red-300",
  revision: "bg-amber-900 text-amber-300",
  cancelled: "bg-slate-800 text-slate-400",
  paused: "bg-amber-900 text-amber-300",
  terminated: "bg-red-950 text-red-400",
  failed: "bg-red-900 text-red-300",
  completed: "bg-slate-700 text-slate-200",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "승인 대기",
  pending_approval: "승인 대기",
  processing: "처리중",
  in_progress: "진행중",
  approved: "승인됨",
  rejected: "반려됨",
  revision: "보완 요청",
  cancelled: "취소됨",
  paused: "정지됨",
  terminated: "강제 종료됨",
  failed: "실패",
  completed: "완료",
};

// 이 상태일 때는 detail 화면이 자동으로 폴링해서 실시간으로 갱신한다.
const LIVE_STATUSES = new Set(["in_progress", "pending_approval"]);

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

  const [decidingId, setDecidingId] = useState<string | null>(null);
  const [commentDraft, setCommentDraft] = useState<{ id: string; decision: "revision" | "rejected" } | null>(null);
  const [revisionComment, setRevisionComment] = useState("");

  const [editingDirective, setEditingDirective] = useState(false);
  const [directiveDraft, setDirectiveDraft] = useState("");
  const [savingDirective, setSavingDirective] = useState(false);

  const [uploadingMedia, setUploadingMedia] = useState(false);
  const [mediaCaptionDraftId, setMediaCaptionDraftId] = useState<string | null>(null);
  const [mediaCaptionDraft, setMediaCaptionDraft] = useState("");
  const mediaFileInputRef = useRef<HTMLInputElement>(null);

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

  // 처리 중/승인 대기 상태인 동안엔 자동으로 몇 초마다 다시 불러와 실시간처럼 보이게 한다 -
  // 새로고침을 계속 누르지 않아도 진행 상황이 화면에 반영된다. 끝나면(완료/반려/정지 등) 멈춘다.
  useEffect(() => {
    if (!selected || !detail || !LIVE_STATUSES.has(detail.status)) return;
    const timer = setInterval(() => {
      getDirectiveDetail(selected).then(setDetail).catch(() => undefined);
    }, 5000);
    return () => clearInterval(timer);
  }, [selected, detail?.status]);

  const [controlBusy, setControlBusy] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [autoSchedule, setAutoSchedule] = useState<AutoScheduleOut | null>(null);

  const [budget, setBudget] = useState<AiBudgetOut | null>(null);

  useEffect(() => {
    getAutoSchedule().then(setAutoSchedule).catch(() => undefined);
    getAiBudget().then(setBudget).catch(() => undefined);
  }, []);

  const saveBudget = async (patch: Partial<AiBudgetOut>) => {
    try {
      setBudget(await updateAiBudget(patch));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const saveAutoSchedule = async (patch: Partial<AutoScheduleOut>) => {
    try {
      setAutoSchedule(await updateAutoSchedule(patch));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handlePause = async () => {
    if (!selected) return;
    setControlBusy(true);
    try {
      await pauseDirective(selected);
      loadDetail(selected);
    } catch (e) {
      setDetailError((e as Error).message);
    } finally {
      setControlBusy(false);
    }
  };

  const handleResume = async () => {
    if (!selected) return;
    setControlBusy(true);
    try {
      await resumeDirective(selected);
      loadDetail(selected);
    } catch (e) {
      setDetailError((e as Error).message);
    } finally {
      setControlBusy(false);
    }
  };

  const handleTerminate = async () => {
    if (!selected) return;
    if (!window.confirm("정말 강제 종료하시겠습니까? 진행 중인 작업이 취소되고 되돌릴 수 없습니다.")) return;
    setControlBusy(true);
    try {
      await terminateDirective(selected);
      loadDetail(selected);
    } catch (e) {
      setDetailError((e as Error).message);
    } finally {
      setControlBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!selected) return;
    if (!window.confirm("정말 이 업무 지시를 완전히 삭제하시겠습니까? 되돌릴 수 없습니다.")) return;
    setControlBusy(true);
    try {
      await deleteDirective(selected);
      setSelected(null);
      setDetail(null);
      load();
    } catch (e) {
      setDetailError((e as Error).message);
      setControlBusy(false);
    }
  };

  const handleDecide = async (approvalId: string, decision: "approved" | "rejected" | "revision", comment?: string) => {
    if (decision === "approved" && !window.confirm("정말 승인하시겠습니까?")) {
      return;
    }
    setDecidingId(approvalId);
    setDetailError(null);
    try {
      await decideApproval(approvalId, decision, comment);
      setCommentDraft(null);
      setRevisionComment("");
      if (selected) loadDetail(selected);
    } catch (e) {
      setDetailError((e as Error).message);
    } finally {
      setDecidingId(null);
    }
  };

  const handleSaveDirective = async () => {
    if (!selected) return;
    setSavingDirective(true);
    try {
      await updateDirective(selected, directiveDraft);
      setEditingDirective(false);
      loadDetail(selected);
    } catch (e) {
      setDetailError((e as Error).message);
    } finally {
      setSavingDirective(false);
    }
  };

  const handleAddMedia = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selected) return;
    setUploadingMedia(true);
    try {
      await uploadDirectiveMedia(selected, file);
      loadDetail(selected);
    } catch (err) {
      setDetailError((err as Error).message);
    } finally {
      setUploadingMedia(false);
      if (mediaFileInputRef.current) mediaFileInputRef.current.value = "";
    }
  };

  const handleSaveCaption = async (mediaId: string) => {
    if (!selected) return;
    try {
      await updateDirectiveMedia(selected, mediaId, mediaCaptionDraft);
      setMediaCaptionDraftId(null);
      loadDetail(selected);
    } catch (e) {
      setDetailError((e as Error).message);
    }
  };

  const handleDeleteMedia = async (mediaId: string) => {
    if (!selected) return;
    try {
      await deleteDirectiveMedia(selected, mediaId);
      loadDetail(selected);
    } catch (e) {
      setDetailError((e as Error).message);
    }
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
          {detail && <StatusPill status={detail.status} />}
          <span className="text-xs text-slate-500">{selected}</span>
          <div className="ml-auto flex gap-2">
            {detail?.status === "paused" ? (
              <button
                onClick={handleResume}
                disabled={controlBusy}
                className="rounded-md border border-amber-800 px-3 py-1.5 text-sm text-amber-300 hover:bg-amber-950 disabled:opacity-50"
              >
                재개
              </button>
            ) : (
              detail &&
              LIVE_STATUSES.has(detail.status) && (
                <button
                  onClick={handlePause}
                  disabled={controlBusy}
                  className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                >
                  정지
                </button>
              )
            )}
            {detail && detail.status !== "terminated" && (
              <button
                onClick={handleTerminate}
                disabled={controlBusy}
                className="rounded-md border border-red-900 px-3 py-1.5 text-sm text-red-400 hover:bg-red-950 disabled:opacity-50"
              >
                강제 종료
              </button>
            )}
            <button
              onClick={handleDelete}
              disabled={controlBusy}
              className="rounded-md border border-red-900 px-3 py-1.5 text-sm text-red-400 hover:bg-red-950 disabled:opacity-50"
            >
              삭제
            </button>
          </div>
        </div>

        {previewOpen && detail?.outputs?.marketing_post && (
          <PostPreviewModal
            post={detail.outputs.marketing_post as Record<string, unknown>}
            deciding={decidingId !== null}
            onClose={() => setPreviewOpen(false)}
            onDecide={(() => {
              const pendingMarketing = detail.approvals.find(
                (a) => a.status === "pending" && a.target_type === "marketing_post",
              );
              if (!pendingMarketing) return undefined;
              return (decision, comment) => {
                setPreviewOpen(false);
                handleDecide(pendingMarketing.id, decision, comment);
              };
            })()}
          />
        )}

        {detailError && <div className="text-sm text-red-400">{detailError}</div>}

        {detail?.last_error && detail.status === "failed" && (
          <div className="rounded-lg border border-red-900 bg-red-950/40 p-4">
            <div className="mb-1 text-sm font-medium text-red-300">⚠️ 처리 중 오류가 발생해 중단됐습니다</div>
            <div className="whitespace-pre-wrap text-xs text-red-200/90">{detail.last_error}</div>
            <div className="mt-2 text-xs text-slate-400">
              원인을 해결한 뒤 아래 결재 카드에서 다시 결정하거나, 새로 지시해주세요.
            </div>
          </div>
        )}

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
              {editingDirective ? (
                <div className="flex flex-col gap-2">
                  <textarea
                    value={directiveDraft}
                    onChange={(e) => setDirectiveDraft(e.target.value)}
                    rows={4}
                    className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm text-slate-200"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={handleSaveDirective}
                      disabled={savingDirective}
                      className="rounded-md bg-brand-purple px-3 py-1.5 text-sm text-white disabled:opacity-50"
                    >
                      저장
                    </button>
                    <button
                      onClick={() => setEditingDirective(false)}
                      className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
                    >
                      취소
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="whitespace-pre-wrap text-sm text-slate-100">{detail.ceo_directive}</div>
                  <button
                    onClick={() => {
                      setDirectiveDraft(detail.ceo_directive);
                      setEditingDirective(true);
                    }}
                    className="mt-2 text-xs text-slate-500 underline hover:text-slate-300"
                  >
                    지시사항 수정 (기록만 수정됨 — 실제 반영은 아래 결정사항에서 승인/보완으로)
                  </button>
                </>
              )}
              <div className="mt-2 text-xs text-slate-500">{formatDate(detail.created_at)} 제출</div>

              <div className="mt-4">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-400">
                    첨부 파일 {detail.media.length > 0 && `(${detail.media.length}개)`}
                  </span>
                  <button
                    onClick={() => mediaFileInputRef.current?.click()}
                    disabled={uploadingMedia}
                    className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                  >
                    {uploadingMedia ? "업로드중..." : "+ 첨부 추가"}
                  </button>
                  <input
                    ref={mediaFileInputRef}
                    type="file"
                    accept="image/*,video/*"
                    hidden
                    onChange={handleAddMedia}
                  />
                </div>
                {detail.media.length === 0 ? (
                  <div className="text-xs text-slate-500">첨부된 파일이 없습니다.</div>
                ) : (
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
                    {detail.media.map((m) => (
                      <div key={m.id} className="rounded border border-slate-800 bg-slate-800/50 p-1.5 text-xs">
                        {m.media_type === "image" ? (
                          <img src={m.url} className="mb-1 aspect-square w-full rounded object-cover" />
                        ) : (
                          <video src={m.url} controls className="mb-1 aspect-square w-full rounded object-cover" />
                        )}
                        {mediaCaptionDraftId === m.id ? (
                          <input
                            value={mediaCaptionDraft}
                            onChange={(e) => setMediaCaptionDraft(e.target.value)}
                            onBlur={() => handleSaveCaption(m.id)}
                            onKeyDown={(e) => e.key === "Enter" && handleSaveCaption(m.id)}
                            autoFocus
                            className="w-full rounded border border-slate-700 bg-slate-900 px-1 py-0.5 text-slate-200"
                          />
                        ) : (
                          <div
                            onClick={() => {
                              setMediaCaptionDraftId(m.id);
                              setMediaCaptionDraft(m.caption ?? "");
                            }}
                            className="mb-1 truncate text-slate-400 hover:text-slate-200"
                            title={m.caption ?? "캡션 없음"}
                          >
                            {m.caption ?? "캡션 없음"}
                          </div>
                        )}
                        <button
                          onClick={() => handleDeleteMedia(m.id)}
                          className="text-red-400 hover:underline"
                        >
                          삭제
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
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
                        마케팅 콘텐츠
                        <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                          {String(outputs.marketing_post.product ?? "")}
                        </span>
                        <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                          {String(outputs.marketing_post.channel ?? "")}
                        </span>
                        <span className="rounded bg-brand-purple/20 px-2 py-0.5 text-xs text-brand-purple">
                          {outputs.marketing_post.format === "instatoon" ? "인스타툰" : "카드뉴스"}
                        </span>
                      </div>
                      <div className="mb-2 whitespace-pre-wrap text-slate-300">
                        {String(outputs.marketing_post.caption ?? "")}
                      </div>
                      {Array.isArray(outputs.marketing_post.image_urls) && outputs.marketing_post.image_urls.length > 0 && (
                        <>
                          <button
                            onClick={() => setPreviewOpen(true)}
                            className="mb-2 rounded-md bg-brand-purple px-3 py-1.5 text-xs font-medium text-white"
                          >
                            🔍 크게 보고 결재하기
                          </button>
                          <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
                            {(outputs.marketing_post.image_urls as string[]).map((url, i) => (
                              <button key={i} onClick={() => setPreviewOpen(true)}>
                                <img
                                  src={url}
                                  alt={`slide ${i + 1}`}
                                  className={`w-full rounded bg-slate-950 object-contain ${
                                    outputs.marketing_post?.format === "instatoon" ? "aspect-[4/5]" : "aspect-square"
                                  }`}
                                />
                              </button>
                            ))}
                          </div>
                        </>
                      )}
                      {outputs.marketing_post.director_notes ? (
                        <div className="mt-2 text-xs text-slate-500">
                          🎬 디렉터 소견: {String(outputs.marketing_post.director_notes)}
                        </div>
                      ) : null}
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
                      <th className="pb-2 pr-4 font-medium">보완 사유</th>
                      <th className="pb-2 font-medium">동작</th>
                    </tr>
                  </thead>
                  <tbody className="text-slate-300">
                    {detail.approvals.map((a) => (
                      <tr key={a.id} className="border-t border-slate-800">
                        <td className="py-2 pr-4">{DEPT_LABEL[a.target_type] ?? a.target_type}</td>
                        <td className="py-2 pr-4"><StatusPill status={a.status} /></td>
                        <td className="py-2 pr-4 whitespace-nowrap text-slate-500">{formatDate(a.created_at)}</td>
                        <td className="py-2 pr-4">{detail.revision_notes[a.target_type] ?? "-"}</td>
                        <td className="py-2">
                          {a.status !== "pending" ? (
                            "-"
                          ) : commentDraft?.id === a.id ? (
                            <div className="flex flex-col gap-1">
                              <textarea
                                value={revisionComment}
                                onChange={(e) => setRevisionComment(e.target.value)}
                                rows={2}
                                autoFocus
                                placeholder={commentDraft.decision === "revision" ? "보완 사유 / 추가 지시" : "반려 사유"}
                                className="w-44 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200"
                              />
                              <div className="flex gap-1">
                                <button
                                  onClick={() => handleDecide(a.id, commentDraft.decision, revisionComment)}
                                  disabled={decidingId === a.id || !revisionComment.trim()}
                                  className={`rounded-md px-2 py-1 text-xs text-white disabled:opacity-50 ${
                                    commentDraft.decision === "revision" ? "bg-brand-purple" : "bg-red-800"
                                  }`}
                                >
                                  {decidingId === a.id ? "제출중..." : commentDraft.decision === "revision" ? "보완 요청" : "반려"}
                                </button>
                                <button
                                  onClick={() => setCommentDraft(null)}
                                  className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
                                >
                                  취소
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div className="flex gap-1">
                              <button
                                onClick={() => handleDecide(a.id, "approved")}
                                disabled={decidingId === a.id}
                                className="rounded-md bg-brand-purple px-2 py-1 text-xs text-white disabled:opacity-50"
                              >
                                승인
                              </button>
                              <button
                                onClick={() => {
                                  setCommentDraft({ id: a.id, decision: "revision" });
                                  setRevisionComment("");
                                }}
                                disabled={decidingId === a.id}
                                className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
                              >
                                보완
                              </button>
                              <button
                                onClick={() => {
                                  setCommentDraft({ id: a.id, decision: "rejected" });
                                  setRevisionComment("");
                                }}
                                disabled={decidingId === a.id}
                                className="rounded-md border border-red-900 px-2 py-1 text-xs text-red-400 hover:bg-red-950"
                              >
                                반려
                              </button>
                            </div>
                          )}
                        </td>
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

      {budget && (
        <div
          className={`flex flex-wrap items-center gap-4 rounded-lg border p-4 ${
            budget.enabled ? "border-slate-800 bg-slate-900" : "border-red-900 bg-red-950/30"
          }`}
        >
          <div className="text-sm font-medium text-slate-200">AI 사용 한도</div>
          <div className="flex items-center gap-2 text-sm">
            <span className="text-xs text-slate-500">오늘 이미지</span>
            <span
              className={
                budget.used_images_today >= budget.daily_image_limit ? "text-red-400" : "text-slate-200"
              }
            >
              {budget.used_images_today} / {budget.daily_image_limit}장
            </span>
            <select
              value={budget.daily_image_limit}
              onChange={(e) => saveBudget({ daily_image_limit: Number(e.target.value) })}
              className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs"
            >
              {[10, 20, 40, 80, 200].map((n) => (
                <option key={n} value={n}>
                  상한 {n}장
                </option>
              ))}
            </select>
          </div>
          <div className="text-xs text-slate-500">
            지시 1건당 최대 {budget.per_thread_image_limit}장 · 오늘 토큰{" "}
            {budget.used_tokens_today.toLocaleString()} / {budget.daily_token_limit.toLocaleString()}
          </div>
          <button
            onClick={() => saveBudget({ enabled: !budget.enabled })}
            className={`ml-auto rounded-md px-3 py-1.5 text-sm ${
              budget.enabled
                ? "border border-red-900 text-red-400 hover:bg-red-950"
                : "bg-red-800 text-white"
            }`}
          >
            {budget.enabled ? "🛑 AI 비상 정지" : "정지 해제 (현재 전면 차단 중)"}
          </button>
        </div>
      )}

      {autoSchedule && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-800 bg-slate-900 p-4">
          <label className="flex items-center gap-2 text-sm text-slate-200">
            <input
              type="checkbox"
              checked={autoSchedule.enabled}
              onChange={(e) => saveAutoSchedule({ enabled: e.target.checked })}
              className="h-4 w-4"
            />
            정기 자동 발행
          </label>
          <span className="text-xs text-slate-500">
            켜두면 지시하지 않아도 앱을 번갈아가며 콘텐츠를 만들어 결재에 올립니다 (게시는 승인 후에만)
          </span>
          <div className="ml-auto flex items-center gap-2 text-sm text-slate-300">
            <span className="text-xs text-slate-500">주기</span>
            <select
              value={autoSchedule.interval_hours}
              onChange={(e) => saveAutoSchedule({ interval_hours: Number(e.target.value) })}
              className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm"
            >
              <option value={24}>매일</option>
              <option value={72}>3일마다</option>
              <option value={168}>주 1회</option>
              <option value={336}>2주마다</option>
            </select>
            {autoSchedule.last_run_at && (
              <span className="text-xs text-slate-500">
                최근 {new Date(autoSchedule.last_run_at).toLocaleString("ko-KR")}
                {autoSchedule.last_product ? ` · ${autoSchedule.last_product}` : ""}
              </span>
            )}
          </div>
        </div>
      )}

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
