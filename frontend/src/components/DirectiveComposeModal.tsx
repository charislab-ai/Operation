import { useEffect, useRef, useState } from "react";
import { submitRichDirective, type DirectiveOut } from "../lib/api";

export default function DirectiveComposeModal({
  onClose,
  onSubmitted,
}: {
  onClose: () => void;
  onSubmitted: (d: DirectiveOut) => void;
}) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const handleSubmit = async () => {
    if (!text.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await submitRichDirective(text.trim(), files);
      onSubmitted(result);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[90vh] w-full max-w-2xl flex-col gap-3 overflow-hidden rounded-lg bg-slate-900 p-5"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-slate-300">새 지시</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300">
            ✕
          </button>
        </div>

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={6}
          autoFocus
          placeholder="CEO 지시를 입력하세요 (예: SnapTale 여름 프로모션 카드뉴스 만들어서 인스타에 올려)"
          className="rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-brand-purple focus:outline-none"
        />

        <button
          onClick={() => fileInputRef.current?.click()}
          className="self-start rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
        >
          + 이미지/동영상 첨부
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,video/*"
          multiple
          hidden
          onChange={(e) => {
            setFiles((prev) => [...prev, ...Array.from(e.target.files ?? [])]);
            if (fileInputRef.current) fileInputRef.current.value = "";
          }}
        />

        {files.length > 0 && (
          <ul className="flex flex-wrap gap-2">
            {files.map((f, i) => (
              <li
                key={i}
                className="flex items-center gap-1.5 rounded bg-slate-800 px-2 py-1 text-xs text-slate-300"
              >
                {f.name}
                <button
                  onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                  className="text-slate-500 hover:text-red-400"
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}

        {error && <div className="text-xs text-red-400">{error}</div>}

        <div className="mt-2 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
          >
            취소
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !text.trim()}
            className="rounded-md bg-brand-purple px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {submitting ? "전송중..." : "지시 등록"}
          </button>
        </div>
      </div>
    </div>
  );
}
