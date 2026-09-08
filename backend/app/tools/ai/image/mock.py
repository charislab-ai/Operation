from io import BytesIO

from PIL import Image


class MockImageGenProvider:
    """ImageGenProvider 구현체 — OPENAI_API_KEY 발급 전까지 쓰는 기본 어댑터 (SOCIAL_ADAPTER=mock과 동일 철학)."""

    async def generate_bytes(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> bytes:
        img = Image.new("RGB", (1024, 1024), (136, 106, 255))
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
