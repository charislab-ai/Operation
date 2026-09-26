import { useEffect, useMemo, useState } from "react";
import { listEmployees, updateEmployee, type EmployeeOut } from "../../lib/api";

/** 직원 명단 - AI 에이전트들을 직원으로 보여준다.
 *  CEO가 이름을 지어주면 지시문에서 그 이름을 부를 때 그 직원만 자기 지시로 받아들인다. */

const STATUS_META: Record<EmployeeOut["status"], { label: string; cls: string }> = {
  active: { label: "재직", cls: "bg-emerald-900/50 text-emerald-300 border-emerald-800" },
  onboarding: { label: "입사 예정", cls: "bg-amber-900/40 text-amber-300 border-amber-800" },
  leave: { label: "대기", cls: "bg-slate-800 text-slate-400 border-slate-700" },
};

const DEPARTMENT_ORDER = ["경영", "마케팅", "디자인", "품질", "개발"];

/** 마케팅 지시 하나가 흐르는 순서 - 화면 위쪽 흐름도에 쓴다. */
const FLOW: { keys: string[]; note: string }[] = [
  { keys: ["supervisor"], note: "지시 접수·부서 배정" },
  { keys: ["performance_marketer"], note: "무엇을 누구에게" },
  { keys: ["marketing_director"], note: "구성 설계" },
  { keys: ["copywriter", "social_editor", "photo_art_director", "layout_designer"], note: "동시에 작업" },
  { keys: ["marketing_director"], note: "조립·최종 검토" },
  { keys: ["brand_qa"], note: "완성 카드 실물 검수" },
  { keys: ["publisher"], note: "CEO 승인 후 게시" },
];

function timeAgo(iso: string | null): string {
  if (!iso) return "기록 없음";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "방금";
  if (mins < 60) return `${mins}분 전`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}시간 전`;
  return `${Math.floor(hours / 24)}일 전`;
}

function EmployeeCard({
  employee,
  maxRuns,
  onPatch,
}: {
  employee: EmployeeOut;
  maxRuns: number;
  onPatch: (patch: Partial<EmployeeOut>) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(employee.name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const status = STATUS_META[employee.status];

  const run = async (patch: Partial<EmployeeOut>) => {
    setBusy(true);
    setError(null);
    try {
      await onPatch(patch);
      setEditing(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className={`flex flex-col gap-2 rounded-lg border p-4 ${
        employee.status === "active" ? "border-slate-800 bg-slate-900" : "border-slate-800/60 bg-slate-900/40"
      }`}
    >
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          {editing ? (
            <div className="flex gap-1">
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                autoFocus
                onKeyDown={(e) => e.key === "Enter" && run({ name: draft })}
                className="w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-100"
              />
              <button
                onClick={() => run({ name: draft })}
                disabled={busy}
                className="rounded bg-brand-purple px-2 text-xs text-white disabled:opacity-50"
              >
                저장
              </button>
              <button
                onClick={() => {
                  setDraft(employee.name);
                  setEditing(false);
                }}
                className="rounded border border-slate-700 px-2 text-xs text-slate-400"
              >
                취소
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-1.5">
              <span className="truncate text-base font-semibold text-slate-100">{employee.name}</span>
              <button
                onClick={() => setEditing(true)}
                title="이름 바꾸기"
                className="text-xs text-slate-600 hover:text-slate-300"
              >
                ✎
              </button>
              {employee.working && (
                <span className="flex items-center gap-1 text-[11px] text-emerald-400">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                  업무중
                </span>
              )}
            </div>
          )}
          <div className="mt-0.5 text-xs text-slate-400">
            {employee.rank} · {employee.title}
          </div>
        </div>
        <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[11px] ${status.cls}`}>{status.label}</span>
      </div>

      <div className="text-xs leading-relaxed text-slate-400">{employee.responsibilities}</div>

      <div className="mt-auto flex flex-col gap-1.5 pt-1">
        <div className="flex items-center gap-2 text-[11px] text-slate-500">
          <span className="w-16 shrink-0">최근 7일</span>
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full rounded-full bg-brand-purple"
              style={{ width: `${maxRuns ? Math.round((employee.runs_7d / maxRuns) * 100) : 0}%` }}
            />
          </div>
          <span className="w-20 shrink-0 text-right tabular-nums">
            {employee.runs_7d}건 · {(employee.tokens_7d / 1000).toFixed(1)}k
          </span>
        </div>
        <div className="truncate text-[11px] text-slate-600">
          {employee.current_task ? `최근: ${employee.current_task}` : "최근 업무 없음"} · {timeAgo(employee.last_active_at)}
        </div>
        {error && <div className="text-[11px] text-red-400">{error}</div>}
        <div className="flex gap-1.5">
          {employee.status === "onboarding" && (
            <button
              onClick={() => run({ status: "active" })}
              disabled={busy}
              className="rounded border border-emerald-800 bg-emerald-900/30 px-2 py-1 text-[11px] text-emerald-300 hover:bg-emerald-900/60 disabled:opacity-50"
            >
              입사시키기
            </button>
          )}
          {employee.status === "active" && (
            <button
              onClick={() => run({ status: "leave" })}
              disabled={busy}
              className="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-400 hover:bg-slate-800 disabled:opacity-50"
            >
              대기 전환
            </button>
          )}
          {employee.status === "leave" && (
            <button
              onClick={() => run({ status: "active" })}
              disabled={busy}
              className="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-800 disabled:opacity-50"
            >
              복귀
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function EmployeesView() {
  const [employees, setEmployees] = useState<EmployeeOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    listEmployees()
      .then((data) => {
        setEmployees(data);
        setError(null);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const byKey = useMemo(() => new Map(employees.map((e) => [e.agent_key, e])), [employees]);
  const maxRuns = useMemo(() => Math.max(1, ...employees.map((e) => e.runs_7d)), [employees]);
  const byDepartment = useMemo(() => {
    const map = new Map<string, EmployeeOut[]>();
    for (const e of employees) map.set(e.department, [...(map.get(e.department) ?? []), e]);
    return [...map.entries()].sort(
      (a, b) => DEPARTMENT_ORDER.indexOf(a[0]) - DEPARTMENT_ORDER.indexOf(b[0]),
    );
  }, [employees]);

  const patch = async (agentKey: string, body: Partial<EmployeeOut>) => {
    const updated = await updateEmployee(agentKey, body);
    setEmployees((prev) => prev.map((e) => (e.agent_key === updated.agent_key ? updated : e)));
  };

  if (loading) return <div className="p-6 text-sm text-slate-400">불러오는 중...</div>;

  return (
    <div className="flex flex-col gap-6 p-6 text-slate-100">
      <div>
        <h1 className="text-lg font-semibold">직원</h1>
        <p className="mt-1 text-xs text-slate-500">
          이름을 바꾸면(✎) 그 이름으로 지시할 수 있습니다 — 지시문에 이름을 부르면 그 직원만 자기
          지시로 받아들이고, 결재 후 "보완"에서 이름을 부르면 그 직원만 다시 작업합니다(나머지
          결과물과 사진은 그대로 재사용되어 추가 비용이 들지 않습니다).
        </p>
      </div>

      {error && <div className="text-sm text-red-400">{error}</div>}

      {/* 업무 흐름도 - 지시 하나가 누구를 거쳐 가는지 */}
      <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950/60 p-4">
        <div className="mb-3 text-xs font-medium text-slate-400">마케팅 지시 하나가 흐르는 길</div>
        <div className="flex min-w-max items-stretch gap-2">
          {FLOW.map((step, i) => {
            const members = step.keys.map((k) => byKey.get(k)).filter(Boolean) as EmployeeOut[];
            if (members.length === 0) return null;
            return (
              <div key={`${step.keys.join()}-${i}`} className="flex items-stretch gap-2">
                <div className="flex w-44 flex-col gap-1 rounded-md border border-slate-800 bg-slate-900 p-2">
                  {members.map((m) => (
                    <div key={m.agent_key} className="flex items-center gap-1.5">
                      <span
                        className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                          m.status === "active"
                            ? m.working
                              ? "animate-pulse bg-emerald-400"
                              : "bg-emerald-700"
                            : m.status === "onboarding"
                              ? "bg-amber-500"
                              : "bg-slate-600"
                        }`}
                      />
                      <span
                        className={`truncate text-xs ${
                          m.status === "active" ? "text-slate-200" : "text-slate-500"
                        }`}
                      >
                        {m.name}
                      </span>
                      {m.status === "onboarding" && (
                        <span className="shrink-0 text-[10px] text-amber-400">입사예정</span>
                      )}
                    </div>
                  ))}
                  <div className="mt-0.5 text-[10px] text-slate-600">{step.note}</div>
                </div>
                {i < FLOW.length - 1 && <div className="flex items-center text-slate-700">→</div>}
              </div>
            );
          })}
          <div className="flex items-center gap-2">
            <div className="flex w-32 flex-col justify-center rounded-md border border-brand-purple/40 bg-brand-purple/10 p-2">
              <div className="text-xs font-medium text-brand-purple">CEO 결재</div>
              <div className="text-[10px] text-slate-500">승인/보완/반려</div>
            </div>
          </div>
        </div>
      </div>

      {/* 부서별 명단 */}
      {byDepartment.map(([department, members]) => (
        <div key={department}>
          <div className="mb-2 flex items-center gap-2">
            <h2 className="text-sm font-medium text-slate-300">{department}</h2>
            <span className="text-xs text-slate-600">{members.length}명</span>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {members.map((e) => (
              <EmployeeCard
                key={e.agent_key}
                employee={e}
                maxRuns={maxRuns}
                onPatch={(body) => patch(e.agent_key, body)}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
