import json
from functools import lru_cache

from google import genai
from google.genai import types

from app.config import settings
from app.db.ai_usage import log_ai_usage
from app.tools.ai.llm.base import Message, SchemaT


@lru_cache
def _client() -> genai.Client:
    return genai.Client(api_key=settings.google_gemini_api_key)


def _split_system_and_prompt(messages: list[Message]) -> tuple[str | None, str]:
    system_parts = [m.content for m in messages if m.role == "system"]
    user_parts = [m.content for m in messages if m.role != "system"]
    return ("\n\n".join(system_parts) or None, "\n\n".join(user_parts))


def _log(usage, thread_id: str | None, agent_name: str | None) -> None:
    log_ai_usage(
        thread_id=thread_id,
        agent_name=agent_name,
        provider="gemini",
        kind="llm",
        input_tokens=getattr(usage, "prompt_token_count", None) if usage else None,
        output_tokens=getattr(usage, "candidates_token_count", None) if usage else None,
        total_tokens=getattr(usage, "total_token_count", None) if usage else None,
    )


class GeminiLLMProvider:
    """LLMProvider 구현체 — Claude CLI/API가 둘 다 실패했을 때(크레딧 소진 등) 쓰는 마지막 폴백.

    영수증 OCR(app/tools/ai/vision/gemini_ocr.py)에 이미 쓰던 GOOGLE_GEMINI_API_KEY를 그대로
    재사용한다 - 별도 계정/키 발급이 필요 없어 폴백 경로로 넣기 좋다. Claude와 벤더/모델이 아예
    다르므로 Anthropic 쪽 장애(요금 미납, 서비스 장애 등)에 영향을 안 받는다는 게 핵심 가치.
    """

    async def complete(
        self,
        messages: list[Message],
        *,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> str:
        system, prompt = _split_system_and_prompt(messages)
        response = await _client().aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system),
        )
        _log(response.usage_metadata, thread_id, agent_name)
        return response.text or ""

    async def complete_structured(
        self,
        messages: list[Message],
        schema: type[SchemaT],
        *,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> SchemaT:
        system, prompt = _split_system_and_prompt(messages)
        response = await _client().aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        _log(response.usage_metadata, thread_id, agent_name)
        if response.parsed is not None:
            return response.parsed  # type: ignore[return-value]
        # SDK가 .parsed를 못 채운 경우를 대비한 방어적 폴백 (gemini_ocr.py와 동일한 패턴)
        return schema.model_validate(json.loads(response.text))
