from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graphs.human_approval import make_approval_node, make_route_after_approval
from app.graphs.state import OSState
from app.graphs.supervisor import route_after_supervisor, supervisor_node
from app.graphs.workers.content_strategist import content_strategist_node
from app.graphs.workers.dev_worker import dev_worker_node
from app.graphs.workers.marketing_director import marketing_director_brief_node, marketing_synthesis_node
from app.graphs.workers.publish_worker import publish_worker_node
from app.graphs.workers.visual_designer import visual_designer_node


def build_graph(checkpointer) -> CompiledStateGraph:
    graph = StateGraph(OSState)

    graph.add_node("supervisor", supervisor_node)
    # 마케팅은 팀 구조: 디렉터가 브리핑 → 콘텐츠 전략가/비주얼 디자이너가 진짜 병렬로 각자 작업
    # (서로 다른 state 키에만 쓰므로 reducer 충돌 없음) → 디렉터가 합쳐서 최종 검토
    graph.add_node("marketing_director_brief", marketing_director_brief_node)
    graph.add_node("content_strategist", content_strategist_node)
    graph.add_node("visual_designer", visual_designer_node)
    graph.add_node("marketing_synthesis", marketing_synthesis_node)
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
        ["marketing_director_brief", "dev_worker"],
    )
    # 브리핑 하나가 두 전문가에게 동시에 뻗어나간다 - 고정된 두 대상이라 조건부 엣지 불필요, edge 2개면 충분
    graph.add_edge("marketing_director_brief", "content_strategist")
    graph.add_edge("marketing_director_brief", "visual_designer")
    # 둘 다 synthesis로 향하므로 LangGraph가 둘 다 끝날 때까지 자동으로 기다렸다가 1번만 실행한다(join)
    graph.add_edge("content_strategist", "marketing_synthesis")
    graph.add_edge("visual_designer", "marketing_synthesis")
    graph.add_edge("marketing_synthesis", "marketing_approval")
    graph.add_edge("dev_worker", "dev_approval")
    graph.add_conditional_edges(
        "marketing_approval",
        make_route_after_approval("marketing"),
        ["marketing_director_brief", "publish_worker", END],
    )
    graph.add_conditional_edges("dev_approval", make_route_after_approval("dev"), ["dev_worker", END])
    graph.add_edge("publish_worker", END)

    return graph.compile(checkpointer=checkpointer)
