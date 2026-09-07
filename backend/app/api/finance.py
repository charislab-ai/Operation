import mimetypes
import uuid
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from app.db.supabase_client import get_supabase
from app.tools.ai.vision import get_vision_ocr
from app.tools.telegram_bot import send_approval_request
from app.workers.finance_worker import map_to_journal_entry

router = APIRouter(prefix="/finance", tags=["finance"])

RECEIPTS_BUCKET = "receipts"
SIGNED_URL_TTL_SECONDS = 60 * 60 * 24 * 365  # 1년 — 사내 회계 기록 조회용


class ReceiptUploadOut(BaseModel):
    finance_entry_id: str
    status: str


class FinanceEntryOut(BaseModel):
    id: str
    entry_date: date | None = None
    debit_account: str
    credit_account: str
    amount: float
    category: str | None = None
    vat_flag: bool
    merchant: str | None = None
    status: str
    receipt_url: str | None = None


@router.post("/receipts", response_model=ReceiptUploadOut)
async def upload_receipt(file: UploadFile = File(...)) -> dict:
    image_bytes = await file.read()
    mime_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "image/jpeg"

    supabase = get_supabase()
    bucket = supabase.storage.from_(RECEIPTS_BUCKET)

    storage_path = f"{uuid.uuid4()}_{file.filename or 'receipt'}"
    bucket.upload(storage_path, image_bytes, {"content-type": mime_type})
    signed = bucket.create_signed_url(storage_path, SIGNED_URL_TTL_SECONDS)
    receipt_url = signed.get("signedURL") or signed.get("signedUrl")

    receipt = await get_vision_ocr().extract_receipt(image_bytes, mime_type)
    journal = map_to_journal_entry(receipt)

    entry = (
        supabase.table("finance_entries")
        .insert(
            {
                **journal,
                "receipt_url": receipt_url,
                "status": "draft",
                "raw_ocr": receipt.model_dump(),
            }
        )
        .execute()
    )
    finance_entry_id = entry.data[0]["id"]

    approval = (
        supabase.table("approvals")
        .insert(
            {
                "target_type": "finance_entry",
                "target_id": finance_entry_id,
                "status": "pending",
                "payload": journal,
            }
        )
        .execute()
    )
    approval_id = approval.data[0]["id"]

    message_id = await send_approval_request(approval_id, "finance_entry", journal)
    supabase.table("approvals").update({"telegram_msg_id": str(message_id)}).eq(
        "id", approval_id
    ).execute()

    return {"finance_entry_id": finance_entry_id, "status": "pending_approval"}


@router.get("/entries", response_model=list[FinanceEntryOut])
def list_entries(status: str | None = None) -> list[dict]:
    query = get_supabase().table("finance_entries").select("*").order("entry_date", desc=True)
    if status:
        query = query.eq("status", status)
    return query.execute().data


@router.get("/summary")
def finance_summary() -> list[dict]:
    """대시보드 막대그래프용 — 확정(confirmed)된 분개만 월별로 집계한다.

    Why: PRD.md의 Human-in-the-Loop 정책상 회계 분개는 텔레그램 승인 후에만
    확정되므로, 승인 전(draft) 데이터가 대시보드 수치에 섞이면 안 된다.
    """
    entries = (
        get_supabase()
        .table("finance_entries")
        .select("entry_date, amount")
        .eq("status", "confirmed")
        .execute()
        .data
    )

    monthly: dict[str, float] = defaultdict(float)
    for e in entries:
        entry_date = e.get("entry_date")
        if not entry_date:
            continue
        period = entry_date[:7]  # "YYYY-MM"
        monthly[period] += float(e.get("amount") or 0)

    return [{"period": period, "expense": total} for period, total in sorted(monthly.items())]
