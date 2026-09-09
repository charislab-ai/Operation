import { useEffect, useMemo, useState } from "react";
import { marked } from "marked";
import { getBenchmark, listBenchmarks, type BenchmarkListItem } from "../../lib/api";

export default function MarketingBenchmarksView() {
  const [items, setItems] = useState<BenchmarkListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    listBenchmarks()
      .then((data) => {
        setItems(data);
        setError(null);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const openDetail = (filename: string) => {
    setSelected(filename);
    setDetailLoading(true);
    setDetailError(null);
    getBenchmark(filename)
      .then((d) => setContent(d.content))
      .catch((e) => setDetailError((e as Error).message))
      .finally(() => setDetailLoading(false));
  };

  const grouped = useMemo(() => {
    const byDate = new Map<string, BenchmarkListItem[]>();
    for (const item of items) {
      const list = byDate.get(item.date) ?? [];
      list.push(item);
      byDate.set(item.date, list);
    }
    return Array.from(byDate.entries());
  }, [items]);

  const renderedHtml = useMemo(() => (content ? marked.parse(content, { async: false }) : ""), [content]);

  return (
    <div className="flex h-full gap-0 overflow-hidden text-slate-100">
      <div className="flex w-72 flex-shrink-0 flex-col overflow-auto border-r border-slate-800 p-4">
        <div className="mb-3 flex items-center justify-between">
          <h1 className="text-sm font-semibold">마케팅 리서치</h1>
          <button
            onClick={load}
            className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
          >
            새로고침
          </button>
        </div>
        <div className="mb-3 text-xs text-slate-500">
          하루 2회 자동으로 다른 앱들의 인스타/페이스북 홍보 방식을 조사해 쌓입니다.
        </div>

        {error && <div className="mb-2 text-xs text-red-400">{error}</div>}

        {loading ? (
          <div className="text-sm text-slate-400">불러오는 중...</div>
        ) : items.length === 0 ? (
          <div className="text-sm text-slate-500">아직 쌓인 리포트가 없습니다.</div>
        ) : (
          <div className="flex flex-col gap-4">
            {grouped.map(([date, dayItems]) => (
              <div key={date}>
                <div className="mb-1.5 text-xs font-medium text-slate-500">{date}</div>
                <div className="flex flex-col gap-1">
                  {dayItems.map((item) => (
                    <button
                      key={item.filename}
                      onClick={() => openDetail(item.filename)}
                      className={`rounded-md px-2.5 py-1.5 text-left text-sm ${
                        selected === item.filename
                          ? "bg-brand-purple text-white"
                          : "text-slate-300 hover:bg-slate-800"
                      }`}
                    >
                      {item.time}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-auto p-6">
        {!selected ? (
          <div className="text-sm text-slate-500">왼쪽 목록에서 리포트를 선택하세요.</div>
        ) : detailLoading ? (
          <div className="text-slate-400">불러오는 중...</div>
        ) : detailError ? (
          <div className="text-sm text-red-400">{detailError}</div>
        ) : (
          <div className="max-w-3xl">
            <div
              className="markdown-body rounded-lg border border-slate-800 bg-slate-900 p-6"
              dangerouslySetInnerHTML={{ __html: renderedHtml as string }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
