import { useEffect, useRef, useState, type FormEvent } from "react";
import { submitDirective, getDirective, type DirectiveOut } from "../lib/api";

const STATUS_LABEL: Record<string, string> = {
  completed: "완료",
  pending_approval: "승인 대기중",
  pending: "승인 대기중",
  approved: "승인됨",
  rejected: "반려됨",
  revision: "보완 요청됨",
};

const SETTLED_STATUSES = new Set(["completed", "approved", "rejected"]);

export default function DirectiveBar() {
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [directive, setDirective] = useState<DirectiveOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const pollUntilSettled = (threadId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const updated = await getDirective(threadId);
        setDirective(updated);
        if (SETTLED_STATUSES.has(updated.status) && pollRef.current) {
          clearInterval(pollRef.current);
        }
      } catch {
        if (pollRef.current) clearInterval(pollRef.current);
      }
    }, 4000);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!text.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await submitDirective(text.trim());
      setDirective(result);
      setText("");
      if (!SETTLED_STATUSES.has(result.status)) {
        pollUntilSettled(result.thread_id);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-center gap-3 border-b border-slate-800 bg-slate-950 px-6 py-3"
    >
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="CEO 지시를 입력하세요 (예: SnapTale 여름 프로모션 카드뉴스 만들어서 인스타에 올려)"
        className="flex-1 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-brand-purple focus:outline-none"
      />
      <button
        type="submit"
        disabled={submitting || !text.trim()}
        className="rounded-md bg-brand-purple px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {submitting ? "전송중..." : "지시 등록"}
      </button>
      {directive && (
        <span className="whitespace-nowrap rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-300">
          {STATUS_LABEL[directive.status] ?? directive.status}
        </span>
      )}
      {error && <span className="text-xs text-red-400">{error}</span>}
    </form>
  );
}
