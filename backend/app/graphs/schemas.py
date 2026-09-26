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


class LayoutSpec(BaseModel):
    """카드 한 장의 레이아웃을 "구성 요소의 조합"으로 표현한다 - 고정된 틀 목록 대신 이 조합을
    바꿔가며 벤치마킹에서 발견한 어떤 틀이든 재현하거나 새로 만들 수 있다."""

    background: Literal["photo_full", "ink", "brand_gradient", "paper", "light"] = Field(
        description="배경. photo_full=사진이 화면 전체, ink=짙은 남보라 단색, brand_gradient=브랜드 "
        "컬러 그라디언트, paper=종이 질감(스크랩북/폴라로이드용), light=밝은 뉴트럴"
    )
    photo_style: Literal["full", "card", "polaroid", "circle", "strip", "device", "none"] = Field(
        description="사진 처리. full=화면 가득, card=둥근 카드, polaroid=폴라로이드 프레임, "
        "circle=원형, strip=가로 띠, device=폰 목업처럼 크게(앱 스크린샷 전용), none=사진 없음"
    )
    photo_area: Literal["full", "top", "bottom", "left", "right", "center"] = Field(default="full")
    photo_tilt: int = Field(default=0, description="사진 기울기 -8~8도. 스크랩북/폴라로이드 느낌에만 사용")
    text_panel: Literal["scrim", "white_card", "plain", "note"] = Field(
        default="plain",
        description="텍스트 바탕. scrim=사진 위 어두운 그라데이션, white_card=흰 카드, plain=배경 위 바로, note=메모지",
    )
    text_position: Literal["top", "center", "bottom"] = Field(default="bottom")
    headline_scale: Literal["m", "l", "xl"] = Field(default="l", description="제목 크기. xl은 후킹 슬라이드용")
    accent: Literal["none", "marker", "underline", "number", "quote", "checklist"] = Field(
        default="none",
        description="강조 장치. marker=형광펜, underline=밑줄, number=원형 번호, quote=큰 따옴표, checklist=체크박스",
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
    layout_name: str = Field(
        description="이 슬라이드에 쓸 카드 틀의 이름. 아래 제공되는 '틀 라이브러리'에서 고르면 "
        "그 이름을 그대로 쓰고, 어울리는 게 없어 여러 틀을 조합해 새로 만들었다면 새 이름을 지어 "
        "적을 것(예: '폴라로이드+체크리스트형')"
    )
    layout_spec: LayoutSpec = Field(
        description="이 슬라이드 카드의 실제 레이아웃 설계. 라이브러리에서 고른 틀이면 그 틀의 "
        "spec을 그대로 쓰고, 새로 조합했다면 각 항목을 직접 정할 것"
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
