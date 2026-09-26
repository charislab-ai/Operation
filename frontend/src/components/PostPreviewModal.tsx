import { useEffect, useState } from "react";

/** 승인 전에 카드뉴스/인스타툰을 실제 인스타그램처럼 크게 넘겨보며 결재하는 화면.
 *  예전엔 작은 썸네일만 보여서 CEO가 무엇을 승인하는지 제대로 확인할 수 없었다. */
export default function PostPreviewModal({
  post,
  onClose,
  onDecide,
  deciding,
}: {
  post: Record<string, unknown>;
  onClose: () => void;
  onDecide?: (decision: "approved" | "rejected" | "revision", comment?: string) => void;
  deciding?: boolean;
}) {
  const images = (Array.isArray(post.image_urls) ? post.image_urls : []) as string[];
  const slides = (Array.isArray(post.slides) ? post.slides : []) as Record<string, string>[];
  const isInstatoon = post.format === "instatoon";
  const [index, setIndex] = useState(0);
  const [commentFor, setCommentFor] = useState<"revision" | "rejected" | null>(null);
  const [comment, setComment] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") setIndex((i) => Math.max(0, i - 1));
      if (e.key === "ArrowRight") setIndex((i) => Math.min(images.length - 1, i + 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [images.length, onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4" onClick={onClose}>
      <div
        className="flex max-h-full w-full max-w-5xl gap-6 overflow-auto rounded-lg border border-slate-800 bg-slate-900 p-5"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 좌: 이미지 뷰어 */}
        <div className="flex min-w-0 flex-1 flex-col items-center gap-3">
          <div className="flex w-full items-center gap-2">
            <button
              onClick={() => setIndex((i) => Math.max(0, i - 1))}
              disabled={index === 0}
              className="rounded-md border border-slate-700 px-3 py-6 text-slate-300 disabled:opacity-30"
            >
              ‹
            </button>
            <div className="flex flex-1 items-center justify-center bg-slate-950">
              {images[index] ? (
                <img
                  src={images[index]}
                  alt={`${index + 1}`}
                  className="max-h-[60vh] w-auto object-contain"
                />
              ) : (
                <div className="p-10 text-sm text-slate-500">이미지가 없습니다</div>
              )}
            </div>
            <button
              onClick={() => setIndex((i) => Math.min(images.length - 1, i + 1))}
              disabled={index >= images.length - 1}
              className="rounded-md border border-slate-700 px-3 py-6 text-slate-300 disabled:opacity-30"
            >
              ›
            </button>
          </div>
          <div className="flex gap-1.5">
            {images.map((_, i) => (
              <button
                key={i}
                onClick={() => setIndex(i)}
                className={`h-1.5 w-6 rounded-full ${i === index ? "bg-brand-purple" : "bg-slate-700"}`}
              />
            ))}
          </div>
          <div className="text-xs text-slate-400">
            {index + 1} / {images.length} {isInstatoon ? "컷" : "장"}
            {slides[index] ? ` — ${slides[index].headline ?? ""}` : ""}
          </div>
        </div>

        {/* 우: 캡션 + 결재 */}
        <div className="flex w-80 shrink-0 flex-col gap-3">
          <div className="flex items-center gap-2">
            <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">{String(post.product ?? "")}</span>
            <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">{String(post.channel ?? "")}</span>
            <span className="rounded bg-brand-purple/20 px-2 py-0.5 text-xs text-brand-purple">
              {isInstatoon ? "인스타툰" : "카드뉴스"}
            </span>
          </div>
          <div className="max-h-48 overflow-auto whitespace-pre-wrap rounded border border-slate-800 bg-slate-950 p-3 text-sm text-slate-200">
            {String(post.caption ?? "")}
          </div>
          {post.director_notes ? (
            <div className="text-xs text-slate-500">🎬 {String(post.director_notes)}</div>
          ) : null}

          {onDecide && (
            <div className="mt-auto flex flex-col gap-2">
              {commentFor ? (
                <>
                  <textarea
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    rows={3}
                    autoFocus
                    placeholder={commentFor === "revision" ? "보완 사유 / 추가 지시" : "반려 사유"}
                    className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm text-slate-200"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => onDecide(commentFor, comment)}
                      disabled={deciding || !comment.trim()}
                      className={`flex-1 rounded-md px-3 py-2 text-sm text-white disabled:opacity-50 ${
                        commentFor === "revision" ? "bg-brand-purple" : "bg-red-800"
                      }`}
                    >
                      {deciding ? "제출중..." : commentFor === "revision" ? "보완 요청" : "반려"}
                    </button>
                    <button
                      onClick={() => setCommentFor(null)}
                      className="rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-300"
                    >
                      취소
                    </button>
                  </div>
                </>
              ) : (
                <div className="flex gap-2">
                  <button
                    onClick={() => onDecide("approved")}
                    disabled={deciding}
                    className="flex-1 rounded-md bg-green-800 px-3 py-2 text-sm text-white disabled:opacity-50"
                  >
                    승인
                  </button>
                  <button
                    onClick={() => setCommentFor("revision")}
                    disabled={deciding}
                    className="flex-1 rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-300"
                  >
                    보완
                  </button>
                  <button
                    onClick={() => setCommentFor("rejected")}
                    disabled={deciding}
                    className="flex-1 rounded-md border border-red-900 px-3 py-2 text-sm text-red-400"
                  >
                    반려
                  </button>
                </div>
              )}
            </div>
          )}
          <button onClick={onClose} className="text-xs text-slate-500 underline hover:text-slate-300">
            닫기 (Esc)
          </button>
        </div>
      </div>
    </div>
  );
}
