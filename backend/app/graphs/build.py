from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graphs.human_approval import make_approval_node, make_route_after_approval
from app.graphs.state import OSState
from app.graphs.supervisor import route_after_supervisor, supervisor_node
from app.graphs.workers.bizdev_worker import bizdev_worker_node
from app.graphs.workers.dev_worker import dev_worker_node
from app.graphs.workers.marketing_worker import marketing_worker_node
from app.graphs.workers.pm_worker import pm_worker_node
from app.graphs.workers.publish_worker import publish_worker_node


def build_graph(checkpointer) -> CompiledStateGraph:
    graph = StateGraph(OSState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("bizdev_worker", bizdev_worker_node)
    graph.add_node("pm_worker", pm_worker_node)
    graph.add_node("marketing_worker", marketing_worker_node)
    graph.add_node("dev_worker", dev_worker_node)
    # pm/marketing/dev가 같은 슈퍼스텝에서 병렬 실행될 수 있으므로 승인 노드도 각각 독립적으로
    # 둔다(공유 노드로 두면 LangGraph가 조인으로 취급해 상태가 섞임 - human_approval.py 참고)
    graph.add_node("pm_approval", make_approval_node("pm"))
    graph.add_node("marketing_approval", make_approval_node("marketing"))
    graph.add_node("dev_approval", make_approval_node("dev"))
    graph.add_node("publish_worker", publish_worker_node)

    graph.add_edge(START, "supervisor")
    # route_after_supervisor가 노드 이름 리스트를 반환하면 그 노드들이 같은 슈퍼스텝에서 병렬 실행된다
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        ["bizdev_worker", "pm_worker", "marketing_worker", "dev_worker"],
    )
    graph.add_edge("bizdev_worker", "pm_worker")
    graph.add_edge("pm_worker", "pm_approval")
    graph.add_edge("marketing_worker", "marketing_approval")
    graph.add_edge("dev_worker", "dev_approval")
    graph.add_conditional_edges("pm_approval", make_route_after_approval("pm"), ["pm_worker", END])
    graph.add_conditional_edges(
        "marketing_approval", make_route_after_approval("marketing"), ["marketing_worker", "publish_worker", END]
    )
    graph.add_conditional_edges("dev_approval", make_route_after_approval("dev"), ["dev_worker", END])
    graph.add_edge("publish_worker", END)

    return graph.compile(checkpointer=checkpointer)
