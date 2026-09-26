from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graphs.human_approval import make_approval_node, make_route_after_approval
from app.graphs.state import OSState
from app.graphs.supervisor import route_after_supervisor, supervisor_node
from app.graphs.workers.brand_qa import brand_qa_node
from app.graphs.workers.copywriter import copywriter_node
from app.graphs.workers.dev_worker import dev_worker_node
from app.graphs.workers.layout_designer import layout_designer_node
from app.graphs.workers.marketing_director import marketing_director_brief_node, marketing_synthesis_node
from app.graphs.workers.performance_marketer import performance_marketer_node
from app.graphs.workers.photo_art_director import photo_art_director_node
from app.graphs.workers.publish_worker import publish_worker_node
from app.graphs.workers.social_editor import social_editor_node


def build_graph(checkpointer) -> CompiledStateGraph:
    graph = StateGraph(OSState)

    graph.add_node("supervisor", supervisor_node)
    # 마케팅은 전문가 팀 구조다. 한 명이 여러 직무를 겸하면 지침이 비대해져 뒤쪽 지침을 흘리는
    # 문제가 실측으로 확인돼(사진과 조판을 겸하던 예전 "비주얼 디자이너") 직무별로 나눴다:
    #   퍼포먼스 마케터(입사 예정) → 디렉터 브리핑
    #     → 카피라이터 / 소셜 에디터 / 포토 아트디렉터 / 레이아웃 디자이너 (넷 다 병렬)
    #   → 디렉터 조립 → 브랜드 QA(완성 카드 실물 검수) → CEO 결재
    #
    # 넷을 반드시 "같은 깊이"로 두는 이유(실측 사고): 레이아웃 디자이너를 포토AD 뒤에 한 단계
    # 더 붙였더니 합성 노드가 두 번 실행됐다(먼저 끝난 두 갈래로 한 번, 뒤늦은 갈래로 또 한 번)
    # - 이미지 생성이 통째로 두 번 돌아 비용이 두 배로 나갔고, 같은 스텝에 두 값이 겹치면
    # InvalidUpdateError로 아예 죽었다. 스크린샷을 쓰는 장의 틀 강제(device)는 의존성을 만들지
    # 않고 합성 단계에서 코드로 처리한다(marketing_director.py::_force_device_for_screenshots).
    graph.add_node("performance_marketer", performance_marketer_node)
    graph.add_node("marketing_director_brief", marketing_director_brief_node)
    graph.add_node("copywriter", copywriter_node)
    graph.add_node("social_editor", social_editor_node)
    graph.add_node("photo_art_director", photo_art_director_node)
    graph.add_node("layout_designer", layout_designer_node)
    graph.add_node("marketing_synthesis", marketing_synthesis_node)
    graph.add_node("brand_qa", brand_qa_node)
    graph.add_node("dev_worker", dev_worker_node)
    # pm/marketing/dev가 같은 슈퍼스텝에서 병렬 실행될 수 있으므로 승인 노드도 각각 독립적으로
    # 둔다(공유 노드로 두면 LangGraph가 조인으로 취급해 상태가 섞임 - human_approval.py 참고)
    graph.add_node("marketing_approval", make_approval_node("marketing"))
    graph.add_node("dev_approval", make_approval_node("dev"))
    graph.add_node("publish_worker", publish_worker_node)

    graph.add_edge(START, "supervisor")
    # route_after_supervisor가 노드 이름 리스트를 반환하면 그 노드들이 같은 슈퍼스텝에서 병렬 실행된다
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        ["performance_marketer", "dev_worker"],
    )
    graph.add_edge("performance_marketer", "marketing_director_brief")
    # 브리핑 하나가 세 전문가에게 동시에 뻗어나간다(고정 대상이라 조건부 엣지 불필요)
    graph.add_edge("marketing_director_brief", "copywriter")
    graph.add_edge("marketing_director_brief", "social_editor")
    graph.add_edge("marketing_director_brief", "photo_art_director")
    graph.add_edge("marketing_director_brief", "layout_designer")
    # 네 갈래가 같은 깊이라 한 스텝에 함께 끝나고, synthesis는 정확히 한 번 실행된다.
    # (보완으로 한 명만 다시 돌 때도 그 한 갈래만 끝나고 synthesis가 한 번 실행된다)
    graph.add_edge("copywriter", "marketing_synthesis")
    graph.add_edge("social_editor", "marketing_synthesis")
    graph.add_edge("photo_art_director", "marketing_synthesis")
    graph.add_edge("layout_designer", "marketing_synthesis")
    graph.add_edge("marketing_synthesis", "brand_qa")
    graph.add_edge("brand_qa", "marketing_approval")
    graph.add_edge("dev_worker", "dev_approval")
    graph.add_conditional_edges(
        "marketing_approval",
        make_route_after_approval("marketing"),
        # 보완은 브리핑부터 다시 돌거나(기본), CEO가 이름을 부른 전문가에게만 다시 내려간다.
        [
            "marketing_director_brief",
            "copywriter",
            "social_editor",
            "photo_art_director",
            "layout_designer",
            "publish_worker",
            END,
        ],
    )
    graph.add_conditional_edges("dev_approval", make_route_after_approval("dev"), ["dev_worker", END])
    graph.add_edge("publish_worker", END)

    return graph.compile(checkpointer=checkpointer)
