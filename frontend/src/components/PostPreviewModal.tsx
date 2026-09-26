import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  listLayouts,
  regenerateSlidePhoto,
  renderSlidePreview,
  saveMarketingPost,
  type LayoutOut,
} from "../lib/api";

/** 승인 전에 카드뉴스/인스타툰을 실제 인스타그램처럼 크게 넘겨보며 결재하는 화면.
 *  예전엔 작은 썸네일만 보여서 CEO가 무엇을 승인하는지 제대로 확인할 수 없었다.
 *
 *  여기에 슬라이드 편집기가 붙어 있다: 헤드라인/보조문구/카드 틀을 직접 고치면 AI를 다시
 *  부르지 않고(비용 0, 수 초) 서버가 원본 사진 위에 문구만 다시 얹어 미리보기를 돌려준다.
 *  사진 자체를 바꾸고 싶을 때만 "사진 다시 생성"(유료)을 누른다. 예전엔 한 글자를 고치려 해도
 *  "보완"으로 파이프라인 전체를 다시 돌려야 했다. */

type Slide = Record<string, unknown> & {
  headline?: string;
  subtext?: string;
  layout_name?: string;
  layout_spec?: Record<string, unknown>;
  source_image_url?: string | null;
  image_prompt?: string;
};

export default function PostPreviewModal({
  post,
  onClose,
  onDecide,
  deciding,
  approvalId,
  threadId,
  onSaved,
}: {
  post: Record<string, unknown>;
  onClose: () => void;
  onDecide?: (decision: "approved" | "rejected" | "revision", comment?: string) => void;
  deciding?: boolean;
  /** 결재 대기 중인 카드의 approval id - 있을 때만 편집/저장이 가능하다 */
  approvalId?: string | null;
  threadId?: string;
  onSaved?: () => void;
}) {
  const isInstatoon = post.format === "instatoon";
  const product = String(post.product ?? "");

  const [images, setImages] = useState<string[]>(
    (Array.isArray(post.image_urls) ? post.image_urls : []) as string[],
  );
  const [slides, setSlides] = useState<Slide[]>(
    (Array.isArray(post.slides) ? post.slides : []) as Slide[],
  );
  const [caption, setCaption] = useState(String(post.caption ?? ""));
  const [index, setIndex] = useState(0);
  const [commentFor, setCommentFor] = useState<"revision" | "rejected" | null>(null);
  const [comment, setComment] = useState("");

  const [editing, setEditing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [layouts, setLayouts] = useState<LayoutOut[]>([]);
  const [preview, setPreview] = useState<string | null>(null);
  const [rendering, setRendering] = useState(false);
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const slide = slides[index] ?? {};
  const total = slides.length || images.length;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (editing) return; // 편집 중 화살표는 입력에 쓰이므로 슬라이드를 넘기지 않는다
      if (e.key === "ArrowLeft") setIndex((i) => Math.max(0, i - 1));
      if (e.key === "ArrowRight") setIndex((i) => Math.min(images.length - 1, i + 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [images.length, onClose, editing]);

  useEffect(() => {
    if (editing && layouts.length === 0) listLayouts().then(setLayouts).catch(() => undefined);
  }, [editing, layouts.length]);

  const patchSlide = (patch: Partial<Slide>) => {
    setSlides((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)));
    setDirty(true);
  };

  // 입력이 멈춘 뒤에만 다시 그린다 - 타이핑 한 글자마다 서버를 때리지 않도록 디바운스.
  const renderSeq = useRef(0);
  const refreshPreview = useCallback(async () => {
    const seq = ++renderSeq.current;
    setRendering(true);
    try {
      const url = await renderSlidePreview({
        product,
        format: isInstatoon ? "instatoon" : "card_news",
        page_label: `${index + 1}/${total}`,
        headline: String(slide.headline ?? ""),
        subtext: String(slide.subtext ?? ""),
        layout_spec: (slide.layout_spec as Record<string, unknown>) ?? {},
        source_image_url: (slide.source_image_url as string) ?? null,
      });
      if (seq === renderSeq.current) {
        setPreview(url);
        setEditError(null);
      }
    } catch (e) {
      if (seq === renderSeq.current) setEditError((e as Error).message);
    } finally {
      if (seq === renderSeq.current) setRendering(false);
    }
  }, [product, isInstatoon, index, total, slide.headline, slide.subtext, slide.layout_spec, slide.source_image_url]);

  useEffect(() => {
    if (!editing) {
      setPreview(null);
      return;
    }
    const t = setTimeout(refreshPreview, 400);
    return () => clearTimeout(t);
  }, [editing, refreshPreview]);

  const handleRegenerate = async () => {
    const prompt = String(slide.image_prompt ?? "");
    if (!prompt.trim()) {
      setEditError("사진 지시문을 먼저 입력해주세요");
      return;
    }
    setRegenerating(true);
    setEditError(null);
    try {
      const url = await regenerateSlidePhoto(prompt, threadId);
      patchSlide({ source_image_url: url });
    } catch (e) {
      setEditError((e as Error).message);
    } finally {
      setRegenerating(false);
    }
  };

  const handleSave = async () => {
    if (!approvalId) return;
    setSaving(true);
    setEditError(null);
    try {
      const saved = await saveMarketingPost(approvalId, {
        caption,
        slides: slides.map((s) => ({
          headline: String(s.headline ?? ""),
          subtext: String(s.subtext ?? ""),
          layout_name: String(s.layout_name ?? ""),
          layout_spec: (s.layout_spec as Record<string, unknown>) ?? {},
          source_image_url: (s.source_image_url as string) ?? null,
        })),
      });
      setImages((Array.isArray(saved.image_urls) ? saved.image_urls : []) as string[]);
      setSlides((Array.isArray(saved.slides) ? saved.slides : []) as Slide[]);
      setDirty(false);
      setEditing(false);
      onSaved?.();
    } catch (e) {
      setEditError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const currentImage = editing ? preview : images[index];
  // 편집기 도입 전 카드에는 원본 사진이 없어 문구만 다시 얹을 수 없다(사진이 사라짐) - 서버도 막지만
  // 편집 화면에서 미리 알려준다.
  const needsPhoto =
    isInstatoon || ((slide.layout_spec as Record<string, unknown>)?.photo_style ?? "full") !== "none";
  const layoutOptions = useMemo(() => layouts.filter((l) => l.enabled), [layouts]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4" onClick={onClose}>
      <div
        className="flex max-h-full w-full max-w-6xl gap-6 overflow-auto rounded-lg border border-slate-800 bg-slate-900 p-5"
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
            <div className="relative flex flex-1 items-center justify-center bg-slate-950">
              {currentImage ? (
                <img src={currentImage} alt={`${index + 1}`} className="max-h-[62vh] w-auto object-contain" />
              ) : (
                <div className="p-10 text-sm text-slate-500">{editing ? "다시 그리는 중..." : "이미지가 없습니다"}</div>
              )}
              {editing && rendering && currentImage && (
                <div className="absolute right-2 top-2 rounded bg-black/70 px-2 py-1 text-[11px] text-slate-300">
                  다시 그리는 중...
                </div>
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
            {slides[index]?.headline ? ` — ${String(slides[index].headline)}` : ""}
          </div>
        </div>

        {/* 우: 캡션 + 편집 + 결재 */}
        <div className="flex w-96 shrink-0 flex-col gap-3">
          <div className="flex items-center gap-2">
            <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">{product}</span>
            <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">{String(post.channel ?? "")}</span>
            <span className="rounded bg-brand-purple/20 px-2 py-0.5 text-xs text-brand-purple">
              {isInstatoon ? "인스타툰" : "카드뉴스"}
            </span>
            {approvalId && (
              <button
                onClick={() => setEditing((v) => !v)}
                className="ml-auto rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
              >
                {editing ? "편집 닫기" : "✏️ 편집"}
              </button>
            )}
          </div>

          {editing ? (
            <div className="flex flex-col gap-3 overflow-auto">
              <div className="rounded border border-slate-800 bg-slate-950 p-3">
                <div className="mb-2 text-xs font-medium text-slate-400">
                  {index + 1}번째 {isInstatoon ? "컷" : "장"} 편집
                </div>
                <label className="mb-1 block text-[11px] text-slate-500">
                  {isInstatoon ? "대사(말풍선)" : "헤드라인"}
                </label>
                <input
                  value={String(slide.headline ?? "")}
                  onChange={(e) => patchSlide({ headline: e.target.value })}
                  className="mb-2 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm text-slate-100"
                />
                <label className="mb-1 block text-[11px] text-slate-500">
                  {isInstatoon ? "자막(내레이션)" : "보조 문구"}
                </label>
                <input
                  value={String(slide.subtext ?? "")}
                  onChange={(e) => patchSlide({ subtext: e.target.value })}
                  className="w-full rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm text-slate-100"
                />

                {!isInstatoon && (
                  <>
                    <label className="mb-1 mt-3 block text-[11px] text-slate-500">
                      카드 틀 {slide.layout_name ? `(현재: ${String(slide.layout_name)})` : ""}
                    </label>
                    <select
                      value=""
                      onChange={(e) => {
                        const picked = layoutOptions.find((l) => l.id === e.target.value);
                        if (picked) patchSlide({ layout_name: picked.name, layout_spec: picked.spec });
                      }}
                      className="w-full rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm text-slate-100"
                    >
                      <option value="">틀 바꾸기...</option>
                      {layoutOptions.map((l) => (
                        <option key={l.id} value={l.id}>
                          {l.name} — {l.when_to_use}
                        </option>
                      ))}
                    </select>
                  </>
                )}
              </div>

              <div className="rounded border border-slate-800 bg-slate-950 p-3">
                {needsPhoto && !slide.source_image_url && (
                  <div className="mb-2 rounded border border-amber-900 bg-amber-950/40 px-2 py-1.5 text-[11px] text-amber-300">
                    이 장은 편집기 도입 전에 만들어져 원본 사진이 없습니다 - 저장하려면 사진을 먼저
                    다시 생성해주세요.
                  </div>
                )}
                <label className="mb-1 block text-[11px] text-slate-500">
                  사진 지시문 (바꾸려면 아래 버튼 — AI 생성 비용이 듭니다)
                </label>
                <textarea
                  value={String(slide.image_prompt ?? "")}
                  onChange={(e) => patchSlide({ image_prompt: e.target.value })}
                  rows={3}
                  className="w-full rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200"
                />
                <button
                  onClick={handleRegenerate}
                  disabled={regenerating}
                  className="mt-2 w-full rounded border border-slate-700 px-2 py-1.5 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                >
                  {regenerating ? "사진 생성 중... (30초 내외)" : "🖼 사진만 다시 생성"}
                </button>
              </div>

              <div>
                <label className="mb-1 block text-[11px] text-slate-500">캡션</label>
                <textarea
                  value={caption}
                  onChange={(e) => {
                    setCaption(e.target.value);
                    setDirty(true);
                  }}
                  rows={6}
                  className="w-full rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm text-slate-200"
                />
              </div>

              {editError && <div className="text-xs text-red-400">{editError}</div>}

              <button
                onClick={handleSave}
                disabled={saving || !dirty}
                className="rounded-md bg-brand-purple px-3 py-2 text-sm text-white disabled:opacity-50"
              >
                {saving ? "저장 중... (전체 다시 그리는 중)" : "수정 내용 저장"}
              </button>
            </div>
          ) : (
            <>
              <div className="max-h-48 overflow-auto whitespace-pre-wrap rounded border border-slate-800 bg-slate-950 p-3 text-sm text-slate-200">
                {caption}
              </div>
              {post.director_notes ? (
                <div className="text-xs text-slate-500">🎬 {String(post.director_notes)}</div>
              ) : null}
            </>
          )}

          {onDecide && !editing && (
            <div className="mt-auto flex flex-col gap-2">
              {dirty && (
                <div className="text-xs text-amber-400">
                  저장하지 않은 편집이 있습니다 - 편집 화면에서 저장해야 게시에 반영됩니다.
                </div>
              )}
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
                    disabled={deciding || dirty}
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
