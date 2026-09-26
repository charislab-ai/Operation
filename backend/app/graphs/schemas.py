from typing import Literal

from pydantic import BaseModel, Field


class GoalPlan(BaseModel):
    routes: list[Literal["marketing", "dev"]] = Field(
        description="이 지시를 처리하기 위해 투입할 부서 목록. 홍보 콘텐츠 제작은 marketing, "
        "코드 수정/기능 개발은 dev. 애매하면 marketing."
    )
    worker_briefs: dict[str, str] = Field(
        description="routes에 포함된 각 부서별로 무엇을 해야 하는지 구체적으로 적은 브리핑 "
        "(킥오프 회의 결과라고 생각하고 작성). 부서명을 키로 사용"
    )
    reason: str


class CreativeBrief(BaseModel):
    """마케팅 디렉터가 착수 전 작성 - 콘텐츠 전략가와 비주얼 디자이너가 이 브리핑만 보고
    각자 독립적으로(LangGraph 병렬 노드) 작업하므로 슬라이드 개수·순서·주제를 구체적으로 명시해야 함."""

    product: str = Field(description="ChaMu|SNAPTAIL|터치러쉬 중 홍보 대상 제품 (실제 출시된 제품만)")
    channel: Literal["instagram", "facebook", "tiktok", "threads"]
    format: Literal["card_news", "instatoon"] = Field(
        description="이 게시물의 콘텐츠 형식. card_news=기존 카드뉴스(사진+헤드라인, 정보/기능 전달에 "
        "적합). instatoon=마스코트 캐릭터가 등장하는 말풍선 만화(짧고 공감 가는 에피소드로 자연스럽게 "
        "제품을 소개, 직접적인 기능 나열보다 상황극에 적합) - 최근 유행하는 형식이니 상황과 벤치마킹"
        "인사이트에 맞게 적극적으로 섞어서 고르세요. 매번 같은 형식만 고르면 안 됩니다."
    )
    slide_topics: list[str] = Field(
        description="슬라이드(또는 인스타툰 컷)별로 무엇을 다룰지 한 줄 요약. card_news는 3~5개(1번은 "
        "후킹, 중간은 기능/베네핏 하나씩, 마지막은 CTA), instatoon은 4~6개(기승전결 구조 - 기: 상황 "
        "설정, 승: 공감되는 불편/갈등 심화, 전: 제품으로 해결되는 반전, 결: 만족스러운 마무리+댓글 "
        "유도 질문). 콘텐츠 전략가와 비주얼 디자이너가 서로의 결과물을 못 보고 이 목록만 보고 동시에 "
        "작업하므로 각 컷이 뭘 다루는지 명확하고 구체적으로 적을 것"
    )


class ContentSlide(BaseModel):
    headline: str = Field(description="카드 이미지 안에 크게 들어갈 한글 헤드라인, 15자 내외로 임팩트 있게")
    subtext: str = Field(description="헤드라인 아래 들어갈 보조 설명 문구, 25자 내외")


class ContentStrategy(BaseModel):
    caption: str = Field(description="게시물 전체 캡션/문구 (다운로드 링크는 쓰지 말 것 - 별도로 붙음)")
    slides: list[ContentSlide] = Field(
        description="creative_brief.slide_topics와 정확히 같은 개수·순서로 대응하는 헤드라인/보조문구 목록"
    )


class VisualSlide(BaseModel):
    image_prompt: str = Field(
        description="이 슬라이드 배경으로 쓸 일러스트/사진 생성 프롬프트 - 컬러풀하고 실사에 가까운 "
        "스타일, 텍스트는 이미지 안에 넣지 말 것(헤드라인/보조문구는 별도로 합성됨). "
        "real_screenshot_asset_id를 지정한 슬라이드에서는 이 필드가 쓰이지 않으니 빈 문자열로 둘 것"
    )
    real_screenshot_asset_id: str | None = Field(
        default=None,
        description="제공된 실제 앱 스크린샷 목록 중 이 슬라이드에 쓸 것의 id. 적절한 게 있는 "
        "슬라이드 최대 1~2개에만 지정하고, 나머지는 null로 두어 AI 생성 이미지를 쓰게 할 것",
    )
    layout_style: Literal["banded", "overlay", "bold_type", "split"] = Field(
        default="banded",
        description="card_news 형식일 때만 쓰는 카드 레이아웃 스타일(instatoon이면 이 필드는 쓰이지 "
        "않으니 기본값 그대로 둘 것). banded=사진 위+하단 브랜드컬러 밴드, overlay=풀블리드 사진 위에 "
        "하단 그라데이션과 텍스트 오버레이, bold_type=작은 사진 썸네일+초대형 타이포그래피(후킹 "
        "슬라이드에 효과적), split=좌측 브랜드컬러 블록+텍스트/우측 사진. 최근 벤치마킹 리포트에서 "
        "확인한 인기 있는 카드뉴스 구성 방식을 참고해서 고르고, 한 게시물 안에서도 슬라이드마다 "
        "다양하게 섞어 쓸 것 - 매번 같은 스타일만 고르지 말 것"
    )


class VisualPlan(BaseModel):
    slides: list[VisualSlide] = Field(
        description="creative_brief.slide_topics와 정확히 같은 개수·순서로 대응하는 이미지 프롬프트 목록"
    )


class DirectorReview(BaseModel):
    final_caption: str = Field(description="콘텐츠 전략가의 캡션을 검토해 필요하면 다듬은 최종본")
    director_notes: str = Field(description="검토 소견 1~2문장 - CEO 승인 카드에 노출됨")


class DevProposal(BaseModel):
    title: str
    summary: str = Field(description="무엇을, 왜 바꾸는지 요약")
    files_affected: list[str] = Field(description="수정이 예상되는 파일 경로 목록(추정)")
    code_sketch: str = Field(description="핵심 변경 아이디어를 보여주는 의사코드/스니펫")
    pr_description: str = Field(description="PR 본문 초안")
