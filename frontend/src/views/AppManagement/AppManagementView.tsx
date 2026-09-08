import { useEffect, useRef, useState } from "react";
import {
  deleteProductAsset,
  listProductAssets,
  listProducts,
  updateProduct,
  updateProductAsset,
  uploadProductAsset,
  type ProductAssetOut,
  type ProductOut,
} from "../../lib/api";

interface ProductFormState {
  ios_url: string;
  android_url: string;
  brand_color: string;
  description: string;
}

function toFormState(p: ProductOut): ProductFormState {
  return {
    ios_url: p.ios_url ?? "",
    android_url: p.android_url ?? "",
    brand_color: p.brand_color ?? "",
    description: p.description ?? "",
  };
}

export default function AppManagementView() {
  const [products, setProducts] = useState<ProductOut[]>([]);
  const [assets, setAssets] = useState<ProductAssetOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editingInfoFor, setEditingInfoFor] = useState<string | null>(null);
  const [infoForm, setInfoForm] = useState<ProductFormState | null>(null);
  const [savingInfo, setSavingInfo] = useState(false);

  const [editingAssetId, setEditingAssetId] = useState<string | null>(null);
  const [editingDescription, setEditingDescription] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const [pendingUploadProduct, setPendingUploadProduct] = useState<string | null>(null);
  const [pendingDescription, setPendingDescription] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = () => {
    setLoading(true);
    Promise.all([listProducts(), listProductAssets()])
      .then(([productData, assetData]) => {
        setProducts(productData);
        setAssets(assetData);
        setError(null);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const startEditInfo = (p: ProductOut) => {
    setEditingInfoFor(p.name);
    setInfoForm(toFormState(p));
  };

  const saveInfo = async (name: string) => {
    if (!infoForm) return;
    setSavingInfo(true);
    try {
      await updateProduct(name, infoForm);
      setEditingInfoFor(null);
      setInfoForm(null);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSavingInfo(false);
    }
  };

  const startUpload = (product: string) => {
    setPendingUploadProduct(product);
    setPendingDescription("");
    setTimeout(() => fileInputRef.current?.click(), 0);
  };

  const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    const product = pendingUploadProduct;
    if (!file || !product) return;
    setBusyId(`upload:${product}`);
    setError(null);
    try {
      await uploadProductAsset(product, pendingDescription, file);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
      setPendingUploadProduct(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const startEditAsset = (asset: ProductAssetOut) => {
    setEditingAssetId(asset.id);
    setEditingDescription(asset.description);
  };

  const saveAssetEdit = async (assetId: string) => {
    setBusyId(assetId);
    try {
      await updateProductAsset(assetId, editingDescription);
      setEditingAssetId(null);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  const handleDeleteAsset = async (assetId: string) => {
    setBusyId(assetId);
    try {
      await deleteProductAsset(assetId);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="flex h-full flex-col gap-6 overflow-auto p-6 text-slate-100">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">앱관리</h1>
        <button
          onClick={load}
          className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
        >
          새로고침
        </button>
      </div>

      <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handleFileSelected} />

      {error && <div className="text-sm text-red-400">{error}</div>}

      {loading ? (
        <div className="text-slate-400">불러오는 중...</div>
      ) : products.length === 0 ? (
        <div className="text-sm text-slate-500">등록된 앱이 없습니다.</div>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 xl:grid-cols-3">
          {products.map((p) => {
            const productAssets = assets.filter((a) => a.product === p.name);
            const isUploadingThis = busyId === `upload:${p.name}`;
            const isEditingInfo = editingInfoFor === p.name;

            return (
              <div key={p.id} className="rounded-lg border border-slate-800 bg-slate-900 p-4">
                <div className="mb-3 flex items-center gap-2">
                  <span
                    className="h-4 w-4 flex-shrink-0 rounded-full border border-slate-700"
                    style={{ backgroundColor: p.brand_color ?? "#334155" }}
                  />
                  <h2 className="text-base font-medium text-slate-100">{p.name}</h2>
                </div>

                {isEditingInfo && infoForm ? (
                  <div className="mb-4 flex flex-col gap-2 rounded-md border border-slate-800 bg-slate-950/50 p-3">
                    <label className="text-xs text-slate-500">
                      App Store 링크
                      <input
                        type="text"
                        value={infoForm.ios_url}
                        onChange={(e) => setInfoForm({ ...infoForm, ios_url: e.target.value })}
                        className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200"
                      />
                    </label>
                    <label className="text-xs text-slate-500">
                      Google Play 링크
                      <input
                        type="text"
                        value={infoForm.android_url}
                        onChange={(e) => setInfoForm({ ...infoForm, android_url: e.target.value })}
                        className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200"
                      />
                    </label>
                    <label className="text-xs text-slate-500">
                      브랜드 컬러 (#RRGGBB)
                      <div className="mt-1 flex items-center gap-2">
                        <input
                          type="color"
                          value={/^#[0-9a-fA-F]{6}$/.test(infoForm.brand_color) ? infoForm.brand_color : "#886AFF"}
                          onChange={(e) => setInfoForm({ ...infoForm, brand_color: e.target.value })}
                          className="h-8 w-10 rounded border border-slate-700 bg-slate-800"
                        />
                        <input
                          type="text"
                          value={infoForm.brand_color}
                          onChange={(e) => setInfoForm({ ...infoForm, brand_color: e.target.value })}
                          className="flex-1 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200"
                        />
                      </div>
                    </label>
                    <label className="text-xs text-slate-500">
                      앱 설명 (마케팅 콘텐츠 생성 시 참고)
                      <textarea
                        value={infoForm.description}
                        onChange={(e) => setInfoForm({ ...infoForm, description: e.target.value })}
                        rows={3}
                        className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200"
                      />
                    </label>
                    <div className="mt-1 flex gap-2">
                      <button
                        onClick={() => saveInfo(p.name)}
                        disabled={savingInfo}
                        className="flex-1 rounded-md bg-brand-purple px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                      >
                        저장
                      </button>
                      <button
                        onClick={() => {
                          setEditingInfoFor(null);
                          setInfoForm(null);
                        }}
                        className="flex-1 rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
                      >
                        취소
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="mb-4 flex flex-col gap-1.5 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-500">App Store</span>
                      {p.ios_url ? (
                        <a href={p.ios_url} target="_blank" rel="noreferrer" className="truncate text-brand-purple hover:underline">
                          {p.ios_url}
                        </a>
                      ) : (
                        <span className="text-slate-600">미등록</span>
                      )}
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-500">Google Play</span>
                      {p.android_url ? (
                        <a href={p.android_url} target="_blank" rel="noreferrer" className="truncate text-brand-purple hover:underline">
                          {p.android_url}
                        </a>
                      ) : (
                        <span className="text-slate-600">미등록</span>
                      )}
                    </div>
                    {p.description && <div className="mt-1 text-xs text-slate-400">{p.description}</div>}
                    <button
                      onClick={() => startEditInfo(p)}
                      className="mt-2 self-start rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800"
                    >
                      앱 정보 수정
                    </button>
                  </div>
                )}

                <div className="mb-2 flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-400">스크린샷</span>
                  <button
                    onClick={() => startUpload(p.name)}
                    disabled={isUploadingThis}
                    className="rounded-md bg-brand-purple px-2.5 py-1 text-xs font-medium text-white disabled:opacity-50"
                  >
                    {isUploadingThis ? "등록중..." : "+ 스크린샷"}
                  </button>
                </div>

                {pendingUploadProduct === p.name && (
                  <input
                    type="text"
                    autoFocus
                    value={pendingDescription}
                    onChange={(e) => setPendingDescription(e.target.value)}
                    placeholder="화면 설명 (예: 앨범 목록 화면) — 입력 후 파일 선택"
                    className="mb-3 w-full rounded-md border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 placeholder:text-slate-500"
                  />
                )}

                {productAssets.length === 0 ? (
                  <div className="text-sm text-slate-500">등록된 스크린샷이 없습니다.</div>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    {productAssets.map((a) => (
                      <div key={a.id} className="overflow-hidden rounded-md border border-slate-800 bg-slate-800/50">
                        <img src={a.url} alt={a.description} className="aspect-square w-full object-cover" />
                        <div className="p-2">
                          {editingAssetId === a.id ? (
                            <div className="flex flex-col gap-1.5">
                              <input
                                type="text"
                                autoFocus
                                value={editingDescription}
                                onChange={(e) => setEditingDescription(e.target.value)}
                                className="w-full rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-xs text-slate-200"
                              />
                              <div className="flex gap-1">
                                <button
                                  onClick={() => saveAssetEdit(a.id)}
                                  disabled={busyId === a.id}
                                  className="flex-1 rounded bg-brand-purple px-1.5 py-1 text-xs text-white disabled:opacity-50"
                                >
                                  저장
                                </button>
                                <button
                                  onClick={() => setEditingAssetId(null)}
                                  className="flex-1 rounded border border-slate-700 px-1.5 py-1 text-xs text-slate-300 hover:bg-slate-800"
                                >
                                  취소
                                </button>
                              </div>
                            </div>
                          ) : (
                            <>
                              <div className="mb-1.5 truncate text-xs text-slate-300" title={a.description}>
                                {a.description || "(설명 없음)"}
                              </div>
                              <div className="flex gap-1">
                                <button
                                  onClick={() => startEditAsset(a)}
                                  className="flex-1 rounded border border-slate-700 px-1.5 py-1 text-xs text-slate-300 hover:bg-slate-800"
                                >
                                  수정
                                </button>
                                <button
                                  onClick={() => handleDeleteAsset(a.id)}
                                  disabled={busyId === a.id}
                                  className="flex-1 rounded border border-red-900 px-1.5 py-1 text-xs text-red-400 hover:bg-red-950 disabled:opacity-50"
                                >
                                  삭제
                                </button>
                              </div>
                            </>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
