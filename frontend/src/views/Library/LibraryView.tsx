import { useEffect, useState } from "react";
import { downloadBundle, listLibrary, type LibraryItem } from "../../lib/api";

/** 게시 자료실 - 만들어진 콘텐츠의 문구·태그·이미지·영상을 모아 보고 내려받는 화면.
 *
 *  릴스/쇼츠는 CEO가 인스타그램 앱에서 직접 올리며 음악을 고른다(인앱 인기 오디오는 앱에서
 *  올릴 때만 선택 가능하고 도달에 유리함). 그래서 "복사할 문구"와 "내려받을 파일"이 한 화면에
 *  있어야 한다. */

const STATUS_LABEL: Record<string, { text: string; cls: string }> = {
  pending: { text: "결재 대기", cls: "bg-amber-900/40 text-amber-300 border-amber-800" },
  processing: { text: "처리 중", cls: "bg-blue-900/40 text-blue-300 border-blue-800" },
  approved: { text: "승인됨", cls: "bg-emerald-900/40 text-emerald-300 border-emerald-800" },
  rejected: { text: "반려", cls: "bg-red-900/30 text-red-300 border-red-900" },
  revision: { text: "보완 요청", cls: "bg-slate-800 text-slate-300 border-slate-700" },
  cancelled: { text: "종료", cls: "bg-slate-800 text-slate-500 border-slate-700" },
};

function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  if (!text) return null;
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        } catch {
          /* 클립보드 권한이 없으면 사용자가 직접 선택해 복사 */
        }
      }}
      className="rounded border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300 hover:bg-slate-800"
    >
      {done ? "복사됨 ✓" : label}
    </button>
  );
}

export default function LibraryView() {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    listLibrary()
      .then(setItems)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-6 text-sm text-slate-400">불러오는 중...</div>;

  return (
    <div className="flex flex-col gap-4 p-6 text-slate-100">
      <div>
        <h1 className="text-lg font-semibold">게시 자료실</h1>
        <p className="mt-1 text-xs text-slate-500">
          만들어진 콘텐츠의 문구·해시태그·카드 이미지·쇼츠 영상을 모아둡니다. 릴스는 인스타그램
          앱에서 직접 올리면서 음악을 고르시는 게 도달에 유리해서, 여기서 파일을 받아 쓰시면 됩니다.
        </p>
      </div>

      {error && <div className="text-sm text-red-400">{error}</div>}
      {items.length === 0 && <div className="text-sm text-slate-500">아직 만들어진 콘텐츠가 없습니다.</div>}

      <div className="flex flex-col gap-3">
        {items.map((item) => {
          const status = STATUS_LABEL[item.status] ?? {
            text: item.status,
            cls: "bg-slate-800 text-slate-300 border-slate-700",
          };
          const open = openId === item.approval_id;
          return (
            <div key={item.approval_id} className="rounded-lg border border-slate-800 bg-slate-900">
              <button
                onClick={() => setOpenId(open ? null : item.approval_id)}
                className="flex w-full items-center gap-3 p-4 text-left"
              >
                {item.image_urls[0] && (
                  <img
                    src={item.image_urls[0]}
                    alt=""
                    className="h-16 w-16 flex-shrink-0 rounded object-cover"
                  />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-slate-100">{item.product}</span>
                    <span className="text-xs text-slate-500">{item.channel}</span>
                    <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">
                      {item.format === "instatoon" ? "인스타툰" : "카드뉴스"}
                    </span>
                    <span className={`rounded border px-1.5 py-0.5 text-[10px] ${status.cls}`}>{status.text}</span>
                    {item.video_url && (
                      <span className="rounded bg-brand-purple/20 px-1.5 py-0.5 text-[10px] text-brand-purple">
                        🎬 쇼츠
                      </span>
                    )}
                  </div>
                  <div className="mt-1 truncate text-xs text-slate-500">
                    {(item.caption ?? "").slice(0, 80) || "문구 없음"}
                  </div>
                </div>
                <div className="flex flex-shrink-0 flex-col items-end gap-1">
                  <span className="text-[11px] text-slate-600">{item.created_at.slice(0, 16).replace("T", " ")}</span>
                  <span className="text-[11px] text-slate-600">
                    카드 {item.image_urls.length}장
                  </span>
                </div>
              </button>

              {open && (
                <div className="border-t border-slate-800 p-4">
                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                    {/* 왼쪽: 파일 */}
                    <div className="flex flex-col gap-3">
                      <div className="flex flex-wrap gap-2">
                        {item.image_urls.map((url, i) => (
                          <a key={url} href={url} target="_blank" rel="noreferrer" className="relative">
                            <img src={url} alt={`${i + 1}`} className="h-28 w-28 rounded border border-slate-800 object-cover" />
                            <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 text-[10px] text-white">
                              {i + 1}
                            </span>
                          </a>
                        ))}
                      </div>
                      {item.video_url && (
                        <video src={item.video_url} controls className="max-h-96 w-auto rounded border border-slate-800" />
                      )}
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          onClick={async () => {
                            setBusyId(item.approval_id);
                            try {
                              await downloadBundle(item);
                            } catch (e) {
                              setError((e as Error).message);
                            } finally {
                              setBusyId(null);
                            }
                          }}
                          disabled={busyId === item.approval_id}
                          className="rounded-md bg-brand-purple px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                        >
                          {busyId === item.approval_id ? "압축 중..." : "⬇ 전체 내려받기 (zip)"}
                        </button>
                        {item.video_url && (
                          <a
                            href={item.video_url}
                            download
                            className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
                          >
                            쇼츠만 받기
                          </a>
                        )}
                        {item.permalink && (
                          <a
                            href={item.permalink}
                            target="_blank"
                            rel="noreferrer"
                            className="text-xs text-brand-purple underline"
                          >
                            게시물 보기
                          </a>
                        )}
                      </div>
                    </div>

                    {/* 오른쪽: 문구 */}
                    <div className="flex flex-col gap-3">
                      <div>
                        <div className="mb-1 flex items-center gap-2">
                          <span className="text-xs font-medium text-slate-400">게시 문구</span>
                          <CopyButton text={item.caption ?? ""} label="본문 복사" />
                        </div>
                        <div className="max-h-64 overflow-auto whitespace-pre-wrap rounded border border-slate-800 bg-slate-950 p-3 text-sm text-slate-200">
                          {item.caption || "문구 없음"}
                        </div>
                      </div>
                      {item.hashtags.length > 0 && (
                        <div>
                          <div className="mb-1 flex items-center gap-2">
                            <span className="text-xs font-medium text-slate-400">
                              해시태그 {item.hashtags.length}개
                            </span>
                            <CopyButton text={item.hashtags.join(" ")} label="태그 복사" />
                            <CopyButton
                              text={`${item.caption ?? ""}\n\n${item.hashtags.join(" ")}`}
                              label="본문+태그 복사"
                            />
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {item.hashtags.map((t) => (
                              <span key={t} className="rounded bg-slate-800 px-1.5 py-0.5 text-[11px] text-slate-300">
                                {t}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {item.qa_summary && (
                        <div className="text-[11px] text-slate-500">🔍 {item.qa_summary}</div>
                      )}
                      {item.director_notes && (
                        <div className="text-[11px] text-slate-500">🎬 {item.director_notes}</div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
