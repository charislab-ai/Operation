from typing import Protocol


class ImageGenProvider(Protocol):
    async def generate_bytes(self, prompt: str) -> bytes:
        """이미지를 생성하고 raw PNG 바이트를 반환한다 (업로드는 호출부 책임)."""
        ...
