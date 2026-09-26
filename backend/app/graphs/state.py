import operator
from typing import Annotated, TypedDict


def _merge_dicts(a: dict, b: dict) -> dict:
    return {**a, **b}


class OSState(TypedDict, total=False):
    ceo_directive: str
    active_departments: list[str]  # "marketing"|"dev" 중 이번 지시에 투입되는 부서들 (Supervisor가 기록)
    worker_briefs: dict[str, str]  # Supervisor가 부서별로 작성한 브리핑(킥오프 결과) - 부서명 -> 지시문
    # 마케팅 팀 - MarketingDirector가 브리핑 작성 → 카피라이터/소셜에디터/포토AD가 병렬로,
    # 레이아웃 디자이너는 포토AD 뒤에 이어서 작업한다. 각자 다른 키에만 쓰므로 reducer가 필요 없고,
    # MarketingSynthesis가 전부 끝난 뒤 합쳐서 marketing_post를 만든다(→ BrandQA 검수 → 결재).
    campaign_plan: dict  # PerformanceMarketer 산출물 (입사 전이면 없음) - 제품/채널/타깃/각도
    creative_brief: dict  # MarketingDirector 작성 (product/channel/format/slide_topics)
    copy_plan: dict  # Copywriter 산출물 (slides[headline, subtext]) - 카드 안 문구
    caption_plan: dict  # SocialEditor 산출물 (caption, hashtags) - 피드 노출용
    photo_plan: dict  # PhotoArtDirector 산출물 (slides[image_prompt, real_screenshot_asset_id])
    layout_plan: dict  # LayoutDesigner 산출물 (slides[layout_name, layout_spec])
    qa_report: dict  # BrandQA 산출물 (verdict/issues/summary) - 완성 카드 실물 검수 결과
    # CEO가 지시문에서 이름을 부른 직원의 agent_key. 그 직원만 "나에게 내려온 지시"로 받아들이고
    # 나머지는 기존 방향을 유지한다(app/graphs/workers/_marketing_shared.py::addressing_note)
    addressed_to: str
    marketing_post: dict  # MarketingSynthesis가 최종 조립(product/channel/caption/slides/image_urls/director_notes)
    dev_proposal: dict  # DevWorker가 생성(title/summary/files_affected/code_sketch/pr_description), Phase 4
    # 부서별 승인 결과("approved"|"rejected"|"revision") - 병렬 승인이 서로 안 섞이게 부서명으로 구분.
    # interrupt 재개 시 이미 완료된 다른 부서의 승인 노드도 캐시된 값으로 같은 틱에 다시 완료 처리되면서
    # 함께 이 키를 쓸 수 있어(LangGraph의 재개 재실행 특성) reducer가 필요함
    decisions: Annotated[dict[str, str], _merge_dicts]
    # 보완(revision) 선택 시 CEO가 텔레그램 답장으로 남긴 사유 - 부서별로 구분(같은 이유로 reducer 필요).
    # 해당 Worker가 재실행될 때 이걸 브리핑에 반영해야 진짜로 "보완"이 된다.
    revision_notes: Annotated[dict[str, str], _merge_dicts]
    pending_approvals: list[dict]
    marketing_metrics_summary: dict  # MarketingWorker가 갱신 (Phase 3), Supervisor 라우팅 근거
    # 여러 Worker가 같은 슈퍼스텝에서 동시에 messages를 쓸 수 있어 reducer(자동 합치기)가 필요함
    messages: Annotated[list[dict], operator.add]
