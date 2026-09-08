import operator
from typing import Annotated, TypedDict


def _merge_dicts(a: dict, b: dict) -> dict:
    return {**a, **b}


class OSState(TypedDict, total=False):
    ceo_directive: str
    active_departments: list[str]  # "bizdev"|"pm"|"marketing"|"dev" 중 이번 지시에 동시 투입되는 부서들 (Supervisor가 기록)
    worker_briefs: dict[str, str]  # Supervisor가 부서별로 작성한 브리핑(킥오프 결과) - 부서명 -> 지시문
    biz_plan: dict
    biz_plan_brief: str
    wbs_plan: dict
    marketing_post: dict  # MarketingWorker가 생성(product/channel/caption/image_url), Phase 3
    dev_proposal: dict  # DevWorker가 생성(title/summary/files_affected/code_sketch/pr_description), Phase 4
    # 부서별 승인 결과("approved"|"rejected"|"revision") - 병렬 승인이 서로 안 섞이게 부서명으로 구분.
    # interrupt 재개 시 이미 완료된 다른 부서의 승인 노드도 캐시된 값으로 같은 틱에 다시 완료 처리되면서
    # 함께 이 키를 쓸 수 있어(LangGraph의 재개 재실행 특성) reducer가 필요함
    decisions: Annotated[dict[str, str], _merge_dicts]
    # 보완(revision) 선택 시 CEO가 텔레그램 답장으로 남긴 사유 - 부서별로 구분(같은 이유로 reducer 필요).
    # 해당 Worker가 재실행될 때 이걸 브리핑에 반영해야 진짜로 "보완"이 된다.
    revision_notes: Annotated[dict[str, str], _merge_dicts]
    pending_approvals: list[dict]
    schedule_progress: dict  # PMWorker가 갱신, Supervisor 라우팅 근거 (ARCHITECTURE.md §2)
    marketing_metrics_summary: dict  # MarketingWorker가 갱신 (Phase 3), Supervisor 라우팅 근거
    # 여러 Worker가 같은 슈퍼스텝에서 동시에 messages를 쓸 수 있어 reducer(자동 합치기)가 필요함
    messages: Annotated[list[dict], operator.add]
