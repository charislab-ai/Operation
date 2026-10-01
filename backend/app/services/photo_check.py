"""생성된 사진이 그 장의 내용을 실제로 보여주는지 눈으로 확인한다.

Why: 포토 아트디렉터는 지금까지 "프롬프트를 쓰고 끝"이었다. 생성된 결과를 아무도 보지
않아서, 프롬프트가 아무리 구체적이어도 엉뚱한 사진이 그대로 카드에 들어갔다(실측 사고:
"mp3가 안 열려 답답하다"는 장에 정원에서 수채화 그리는 할머니 사진). 이미지 생성은 같은
프롬프트라도 결과가 들쭉날쭉하므로, 프롬프트를 고치는 것만으로는 막을 수 없다 - 결과물을
봐야 한다.

비용 설계: 확인은 비전 호출(저렴), 재생성은 이미지 생성(비쌈)이라 **재생성 횟수에 상한**을
둔다. 한 장당 1회, 게시물당 _MAX_REGENERATIONS장까지만 다시 만든다.
"""

import base64
import logging

from pydantic import BaseModel, Field

from app.tools.ai.llm import get_llm
from app.tools.ai.llm.base import Message

logger = logging.getLogger(__name__)

MAX_REGENERATIONS = 2  # 게시물당 재생성 상한 - 비용이 선형으로 늘어나는 유일한 지점

_SYSTEM = """당신은 CharisLab의 포토 아트디렉터입니다. 방금 생성된 사진이 이 장에 쓰기에
적합한지 **직접 보고** 판정하세요.

통과(ok=true) 기준 - 아래를 모두 만족할 때만:
1. 사진이 그 장이 말하는 내용을 보여준다(분위기용 사진이 아니라 그 상황이 담겨 있다)
2. 인물이 있다면 머리나 몸이 어색하게 잘리지 않았다
3. 화면 전체가 과도하게 누렇거나 어둡지 않다
4. 사진 안에 글자/로고가 크게 박혀 있지 않다(문구는 나중에 따로 얹으므로 방해가 된다)
5. 기괴하게 왜곡된 손·얼굴 등 AI 생성 특유의 붕괴가 없다

**통과를 기본값으로 두세요.** 완벽한 사진을 요구하는 게 아니라, 쓰면 안 되는 사진을
걸러내는 겁니다. 애매하면 통과시키세요 - 재생성은 비용이 듭니다.

ok=false일 때만 improved_prompt를 쓰세요. 원래 프롬프트에서 **무엇을 바꿔야 문제가
해결되는지**를 반영해 영어로 다시 쓰고, 원래 의도(그 장이 말하려는 내용)는 유지하세요."""


class PhotoVerdict(BaseModel):
    ok: bool = Field(description="이 사진을 그대로 써도 되는가")
    reason: str = Field(description="판정 이유 한 문장(한국어)")
    improved_prompt: str = Field(
        default="", description="ok=false일 때만. 문제를 고친 새 이미지 생성 프롬프트(영어)"
    )


async def verify_photo(
    image_bytes: bytes,
    slide_topic: str,
    headline: str,
    image_prompt: str,
    *,
    thread_id: str | None = None,
) -> PhotoVerdict:
    """사진을 보고 쓸 수 있는지 판정한다. 호출 실패 시에는 통과로 본다(검증 때문에 제작이 멈추면 안 됨)."""
    try:
        return await get_llm().complete_structured(
            [
                Message(role="system", content=_SYSTEM),
                Message(
                    role="user",
                    content=(
                        f"이 장이 말하려는 내용: {slide_topic}\n"
                        f"이 장에 얹힐 문구: {headline}\n"
                        f"사진 생성에 쓴 프롬프트: {image_prompt}\n\n"
                        "위 사진을 보고 판정하세요."
                    ),
                    images=[base64.b64encode(image_bytes).decode()],
                ),
            ],
            PhotoVerdict,
            thread_id=thread_id,
            agent_name="PhotoArtDirector",
        )
    except Exception:
        logger.exception("사진 검증 호출 실패 - 통과로 처리")
        return PhotoVerdict(ok=True, reason="검증을 수행하지 못해 그대로 사용")
