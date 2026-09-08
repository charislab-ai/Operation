from typing import Protocol


class ImageGenProvider(Protocol):
    async def generate_bytes(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> bytes:
        """이미지를 생성하고 raw PNG 바이트를 반환한다 (업로드는 호출부 책임).

        thread_id/agent_name은 업무 지시별 AI 사용량 로깅용 선택적 컨텍스트.
        """
        ...
