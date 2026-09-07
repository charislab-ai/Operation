from typing import Protocol

from pydantic import BaseModel, Field


class ReceiptData(BaseModel):
    merchant: str
    entry_date: str = Field(description="YYYY-MM-DD")
    amount: float
    tax_amount: float = 0
    vat_flag: bool = False
    category: str = Field(description="식비|교통비|사무용품|광고비|기타 중 하나")
    confidence: float = 0.0


class VisionOCRProvider(Protocol):
    async def extract_receipt(self, image: bytes, mime_type: str) -> ReceiptData: ...
