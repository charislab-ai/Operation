import { useEffect, useRef, useState } from "react";
import { getDirective, type DirectiveOut } from "../lib/api";
import DirectiveComposeModal from "./DirectiveComposeModal";

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
  const [open, setOpen] = useState(false);
  const [directive, setDirective] = useState<DirectiveOut | null>(null);
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

  const handleSubmitted = (result: DirectiveOut) => {
    setDirective(result);
    setOpen(false);
    if (!SETTLED_STATUSES.has(result.status)) {
      pollUntilSettled(result.thread_id);
    }
  };

  return (
    <div className="flex items-center gap-3 border-b border-slate-800 bg-slate-950 px-6 py-3">
      <button
        onClick={() => setOpen(true)}
        className="rounded-md bg-brand-purple px-4 py-2 text-sm font-medium text-white"
      >
        + 새 지시
      </button>
      {directive && (
        <span className="whitespace-nowrap rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-300">
          {STATUS_LABEL[directive.status] ?? directive.status}
        </span>
      )}
      {open && <DirectiveComposeModal onClose={() => setOpen(false)} onSubmitted={handleSubmitted} />}
    </div>
  );
}
