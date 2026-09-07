from app.tools.ai.vision.base import ReceiptData

_CATEGORY_TO_DEBIT_ACCOUNT = {
    "식비": "복리후생비",
    "교통비": "여비교통비",
    "사무용품": "소모품비",
    "광고비": "광고선전비",
    "기타": "잡비",
}

_DEFAULT_CREDIT_ACCOUNT = "미지급금"


def map_to_journal_entry(receipt: ReceiptData) -> dict:
    """영수증 OCR 결과(비전 판단)를 복식부기 분개(회계 판단)로 매핑한다.

    OCR과 회계 판단의 책임을 분리해 provider를 섞지 않는다 (ARCHITECTURE.md §7).
    """
    debit_account = _CATEGORY_TO_DEBIT_ACCOUNT.get(receipt.category, _CATEGORY_TO_DEBIT_ACCOUNT["기타"])
    return {
        "entry_date": receipt.entry_date,
        "debit_account": debit_account,
        "credit_account": _DEFAULT_CREDIT_ACCOUNT,
        "amount": receipt.amount,
        "category": receipt.category,
        "vat_flag": receipt.vat_flag,
        "merchant": receipt.merchant,
    }
