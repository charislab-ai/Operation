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

    async def edit_bytes(
        self,
        reference_bytes: bytes,
        prompt: str,
        *,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> bytes:
        """참조 이미지를 기반으로 프롬프트에 맞게 편집한 결과를 반환한다 (마스크 없음 - 전체 이미지를
        참고해서 다시 그림). 인스타툰 마스코트처럼 매번 같은 캐릭터를 유지해야 할 때 사용 -
        처음부터 새로 생성하는 것보다 외형 일관성이 높다(완벽한 픽셀 일치는 아님)."""
        ...
