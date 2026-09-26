import { useEffect, useMemo, useRef, useState } from "react";
import {
  createProduct,
  deleteProductAsset,
  listProductAssets,
  listProducts,
  regenerateMascot,
  screenRecordingToShorts,
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
  mascot_prompt: string;
  tone_of_voice: string;
  target_audience: string;
  key_messages: string;
  banned_words: string;
}

const EMPTY_FORM: ProductFormState = {
  ios_url: "",
  android_url: "",
  brand_color: "",
  description: "",
  mascot_prompt: "",
  tone_of_voice: "",
  target_audience: "",
  key_messages: "",
  banned_words: "",
};

function toFormState(p: ProductOut): ProductFormState {
  return {
    ios_url: p.ios_url ?? "",
    android_url: p.android_url ?? "",
    brand_color: p.brand_color ?? "",
    description: p.description ?? "",
    mascot_prompt: p.mascot_prompt ?? "",
    tone_of_voice: p.tone_of_voice ?? "",
    target_audience: p.target_audience ?? "",
    key_messages: p.key_messages ?? "",
    banned_words: p.banned_words ?? "",
  };
}

function Lightbox({
  assets,
  index,
  onIndexChange,
  onClose,
  onSave,
  onDelete,
  busyId,
}: {
  assets: ProductAssetOut[];
  index: number;
  onIndexChange: (i: number) => void;
  onClose: () => void;
  onSave: (assetId: string, description: string) => Promise<void>;
  onDelete: (assetId: string) => Promise<void>;
  busyId: string | null;
}) {
  const asset = assets[index];
  const [draft, setDraft] = useState(asset.description);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft(asset.description);
  }, [asset.id, asset.description]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft" && index > 0) onIndexChange(index - 1);
      if (e.key === "ArrowRight" && index < assets.length - 1) onIndexChange(index + 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, assets.length, onClose, onIndexChange]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(asset.id, draft);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4"
      onClick={onClose}
    >
      <button
        onClick={onClose}
        className="absolute right-4 top-4 rounded-full bg-slate-800/80 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-700"
      >
        ✕ 닫기
      </button>
      <div className="absolute left-4 top-4 rounded bg-slate-800/80 px-2.5 py-1 text-xs text-slate-300">
        {asset.product} · {index + 1} / {assets.length}
      </div>

      {index > 0 && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onIndexChange(index - 1);
          }}
          className="absolute left-4 top-1/2 -translate-y-1/2 rounded-full bg-slate-800/80 px-3 py-3 text-lg text-slate-200 hover:bg-slate-700"
        >
          ‹
        </button>
      )}
      {index < assets.length - 1 && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onIndexChange(index + 1);
          }}
          className="absolute right-4 top-1/2 -translate-y-1/2 rounded-full bg-slate-800/80 px-3 py-3 text-lg text-slate-200 hover:bg-slate-700"
        >
          ›
        </button>
      )}

      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[90vh] w-full max-w-3xl flex-col gap-3 overflow-hidden rounded-lg bg-slate-900 sm:flex-row"
      >
        <div className="flex flex-1 items-center justify-center bg-slate-950 p-2 sm:max-w-[60%]">
          <img
            src={asset.url}
            alt={asset.description}
            className="max-h-[70vh] w-auto max-w-full object-contain sm:max-h-[86vh]"
          />
        </div>
        <div className="flex w-full flex-col gap-2 p-4 sm:w-80">
          <div className="text-xs text-slate-500">화면 설명</div>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={5}
            className="w-full flex-1 rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-sm text-slate-200"
          />
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={saving || draft === asset.description}
              className="flex-1 rounded-md bg-brand-purple px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {saving ? "저장중..." : "저장"}
            </button>
            <button
              onClick={() => onDelete(asset.id)}
              disabled={busyId === asset.id}
              className="flex-1 rounded-md border border-red-900 px-3 py-1.5 text-sm text-red-400 hover:bg-red-950 disabled:opacity-50"
            >
              삭제
            </button>
          </div>
        </div>
      </div>
    </div>
  );
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
  // 앱 화면 녹화로 만든 쇼츠 URL(제품별) - 업로드 직후 바로 확인할 수 있게
  const [shortsUrl, setShortsUrl] = useState<Record<string, string>>({});

  const [pendingUploadProduct, setPendingUploadProduct] = useState<string | null>(null);
  const [pendingDescription, setPendingDescription] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [showAddForm, setShowAddForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newForm, setNewForm] = useState<ProductFormState>(EMPTY_FORM);
  const [creating, setCreating] = useState(false);

  const [lightbox, setLightbox] = useState<{ product: string; index: number } | null>(null);
  const lightboxAssets = useMemo(
    () => (lightbox ? assets.filter((a) => a.product === lightbox.product) : []),
    [assets, lightbox],
  );

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

  const handleRegenerateMascot = async (name: string) => {
    setBusyId(`mascot:${name}`);
    setError(null);
    try {
      await regenerateMascot(name);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
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

  const openLightbox = (product: string, assetId: string) => {
    const list = assets.filter((a) => a.product === product);
    const index = list.findIndex((a) => a.id === assetId);
    if (index >= 0) setLightbox({ product, index });
  };

  const handleLightboxSave = async (assetId: string, description: string) => {
    try {
      await updateProductAsset(assetId, description);
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const handleLightboxDelete = async (assetId: string) => {
    setBusyId(assetId);
    try {
      await deleteProductAsset(assetId);
      setLightbox(null);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  const handleCreateProduct = async () => {
    if (!newName.trim()) {
      setError("앱 이름을 입력하세요");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      await createProduct({ name: newName.trim(), ...newForm });
      setShowAddForm(false);
      setNewName("");
      setNewForm(EMPTY_FORM);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="flex h-full flex-col gap-6 overflow-auto p-6 text-slate-100">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">앱관리</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setShowAddForm((v) => !v);
              setNewName("");
              setNewForm(EMPTY_FORM);
            }}
            className="rounded-md bg-brand-purple px-3 py-1.5 text-sm font-medium text-white"
          >
            + 앱 추가
          </button>
          <button
            onClick={load}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
          >
            새로고침
          </button>
        </div>
      </div>

      <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handleFileSelected} />

      {showAddForm && (
        <div className="flex flex-col gap-2 rounded-lg border border-slate-800 bg-slate-900 p-4">
          <h2 className="mb-1 text-sm font-medium text-slate-300">새 앱 등록</h2>
          <label className="text-xs text-slate-500">
            앱 이름 (필수, 마케팅 콘텐츠 생성 시 이 이름과 정확히 일치해야 함)
            <input
              type="text"
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="예: 새로운앱"
              className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200"
            />
          </label>
          <label className="text-xs text-slate-500">
            App Store 링크
            <input
              type="text"
              value={newForm.ios_url}
              onChange={(e) => setNewForm({ ...newForm, ios_url: e.target.value })}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200"
            />
          </label>
          <label className="text-xs text-slate-500">
            Google Play 링크
            <input
              type="text"
              value={newForm.android_url}
              onChange={(e) => setNewForm({ ...newForm, android_url: e.target.value })}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200"
            />
          </label>
          <label className="text-xs text-slate-500">
            브랜드 컬러 (#RRGGBB)
            <div className="mt-1 flex items-center gap-2">
              <input
                type="color"
                value={/^#[0-9a-fA-F]{6}$/.test(newForm.brand_color) ? newForm.brand_color : "#886AFF"}
                onChange={(e) => setNewForm({ ...newForm, brand_color: e.target.value })}
                className="h-8 w-10 rounded border border-slate-700 bg-slate-800"
              />
              <input
                type="text"
                value={newForm.brand_color}
                onChange={(e) => setNewForm({ ...newForm, brand_color: e.target.value })}
                className="flex-1 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200"
              />
            </div>
          </label>
          <label className="text-xs text-slate-500">
            앱 설명 (마케팅 콘텐츠 생성 시 참고)
            <textarea
              value={newForm.description}
              onChange={(e) => setNewForm({ ...newForm, description: e.target.value })}
              rows={3}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200"
            />
          </label>
          <div className="mt-1 flex gap-2">
            <button
              onClick={handleCreateProduct}
              disabled={creating}
              className="flex-1 rounded-md bg-brand-purple px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {creating ? "등록중..." : "등록"}
            </button>
            <button
              onClick={() => setShowAddForm(false)}
              className="flex-1 rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
            >
              취소
            </button>
          </div>
        </div>
      )}

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
                    {/* 브랜드북 - 여기 적어두면 카피라이터·소셜에디터·포토AD·레이아웃 디자이너·
                        브랜드 QA가 전부 이 값을 지킨다(매번 톤을 새로 지어내지 않게 하는 장치) */}
                    <div className="mt-2 rounded border border-slate-800 bg-slate-950/60 p-2">
                      <div className="mb-1.5 text-xs font-medium text-slate-400">
                        브랜드북 — 직원 전원이 이 기준을 지킵니다
                      </div>
                      <label className="text-xs text-slate-500">
                        톤앤보이스
                        <input
                          value={infoForm.tone_of_voice}
                          onChange={(e) => setInfoForm({ ...infoForm, tone_of_voice: e.target.value })}
                          placeholder="예: 친근한 반말 대신 편한 존댓말, 과장 없이 담백하게"
                          className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200 placeholder:text-slate-600"
                        />
                      </label>
                      <label className="mt-1.5 block text-xs text-slate-500">
                        핵심 타깃
                        <input
                          value={infoForm.target_audience}
                          onChange={(e) => setInfoForm({ ...infoForm, target_audience: e.target.value })}
                          placeholder="예: 20~30대 아이폰 사용자, 벨소리를 직접 만들고 싶은 사람"
                          className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200 placeholder:text-slate-600"
                        />
                      </label>
                      <label className="mt-1.5 block text-xs text-slate-500">
                        핵심 메시지
                        <input
                          value={infoForm.key_messages}
                          onChange={(e) => setInfoForm({ ...infoForm, key_messages: e.target.value })}
                          placeholder="예: 내 노래를 3분 만에 내 벨소리로"
                          className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200 placeholder:text-slate-600"
                        />
                      </label>
                      <label className="mt-1.5 block text-xs text-slate-500">
                        쓰면 안 되는 표현
                        <input
                          value={infoForm.banned_words}
                          onChange={(e) => setInfoForm({ ...infoForm, banned_words: e.target.value })}
                          placeholder="예: 무료, 최고, 1위 같은 과장 표현"
                          className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200 placeholder:text-slate-600"
                        />
                      </label>
                    </div>
                    <label className="text-xs text-slate-500">
                      인스타툰 마스코트 캐릭터 묘사 (선택, 비워두면 기본 스타일로 생성)
                      <textarea
                        value={infoForm.mascot_prompt}
                        onChange={(e) => setInfoForm({ ...infoForm, mascot_prompt: e.target.value })}
                        rows={2}
                        placeholder="예: 동글동글한 강아지 캐릭터, 파란색 목도리를 두름"
                        className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200 placeholder:text-slate-500"
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

                <div className="mb-4 flex items-center gap-3 rounded-md border border-slate-800 bg-slate-950/50 p-3">
                  <div className="flex h-16 w-16 flex-shrink-0 items-center justify-center overflow-hidden rounded-md bg-slate-800">
                    {p.mascot_url ? (
                      <img src={p.mascot_url} alt={`${p.name} 마스코트`} className="h-full w-full object-contain" />
                    ) : (
                      <span className="text-center text-[10px] text-slate-500">미생성</span>
                    )}
                  </div>
                  <div className="flex flex-1 flex-col gap-1">
                    <span className="text-xs font-medium text-slate-400">인스타툰 마스코트</span>
                    <span className="text-[11px] text-slate-500">
                      캐릭터 묘사를 바꾼 뒤엔 재생성해야 새 모습이 반영됩니다.
                    </span>
                  </div>
                  <button
                    onClick={() => handleRegenerateMascot(p.name)}
                    disabled={busyId === `mascot:${p.name}`}
                    className="flex-shrink-0 rounded-md border border-slate-700 px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                  >
                    {busyId === `mascot:${p.name}` ? "생성중..." : p.mascot_url ? "재생성" : "생성"}
                  </button>
                </div>

                {/* 앱 화면 녹화 → 쇼츠. 실제로 쓰는 화면이 앱 홍보에서 가장 설득력이 높아
                    별도 경로로 둔다. AI를 전혀 쓰지 않아 비용이 없다. */}
                <div className="mb-4 flex items-center gap-3 rounded-md border border-slate-800 bg-slate-950/50 p-3">
                  <div className="flex h-16 w-16 flex-shrink-0 items-center justify-center rounded-md bg-slate-800 text-2xl">
                    🎬
                  </div>
                  <div className="flex flex-1 flex-col gap-1">
                    <span className="text-xs font-medium text-slate-400">앱 화면 녹화 → 쇼츠</span>
                    <span className="text-[11px] text-slate-500">
                      아이폰 화면 녹화를 올리면 세로(9:16)로 맞추고 브랜드 헤더·CTA를 얹어 드립니다.
                    </span>
                    {shortsUrl[p.name] && (
                      <a
                        href={shortsUrl[p.name]}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[11px] text-brand-purple underline"
                      >
                        완성된 쇼츠 보기
                      </a>
                    )}
                  </div>
                  <label className="flex-shrink-0 cursor-pointer rounded-md border border-slate-700 px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800">
                    {busyId === `shorts:${p.name}` ? "변환중..." : "+ 녹화 업로드"}
                    <input
                      type="file"
                      accept="video/*"
                      className="hidden"
                      disabled={busyId === `shorts:${p.name}`}
                      onChange={async (e) => {
                        const file = e.target.files?.[0];
                        e.target.value = "";
                        if (!file) return;
                        setBusyId(`shorts:${p.name}`);
                        setError(null);
                        try {
                          const url = await screenRecordingToShorts(p.name, file, "", 20);
                          setShortsUrl((prev) => ({ ...prev, [p.name]: url }));
                        } catch (err) {
                          setError((err as Error).message);
                        } finally {
                          setBusyId(null);
                        }
                      }}
                    />
                  </label>
                </div>

                <div className="mb-2 flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-400">
                    스크린샷 {productAssets.length > 0 && `(${productAssets.length}장)`}
                  </span>
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
                  <div className="max-h-[520px] overflow-y-auto pr-1">
                    <div className="grid grid-cols-3 gap-2">
                      {productAssets.map((a) => (
                        <div key={a.id} className="overflow-hidden rounded-md border border-slate-800 bg-slate-800/50">
                          <button
                            onClick={() => openLightbox(p.name, a.id)}
                            className="flex aspect-[9/16] w-full items-center justify-center overflow-hidden bg-slate-950"
                          >
                            <img src={a.url} alt={a.description} className="h-full w-full object-contain" />
                          </button>
                          <div className="p-1.5">
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
                                <div
                                  className="mb-1.5 line-clamp-2 min-h-[2.2em] text-[11px] leading-tight text-slate-300"
                                  title={a.description}
                                >
                                  {a.description || "(설명 없음)"}
                                </div>
                                <div className="flex gap-1">
                                  <button
                                    onClick={() => startEditAsset(a)}
                                    className="flex-1 rounded border border-slate-700 px-1 py-1 text-[11px] text-slate-300 hover:bg-slate-800"
                                  >
                                    수정
                                  </button>
                                  <button
                                    onClick={() => handleDeleteAsset(a.id)}
                                    disabled={busyId === a.id}
                                    className="flex-1 rounded border border-red-900 px-1 py-1 text-[11px] text-red-400 hover:bg-red-950 disabled:opacity-50"
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
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {lightbox && lightboxAssets[lightbox.index] && (
        <Lightbox
          assets={lightboxAssets}
          index={lightbox.index}
          onIndexChange={(i) => setLightbox({ product: lightbox.product, index: i })}
          onClose={() => setLightbox(null)}
          onSave={handleLightboxSave}
          onDelete={handleLightboxDelete}
          busyId={busyId}
        />
      )}
    </div>
  );
}
