"""Top-level conversational routing, with versioned persistent graph state."""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from .router import route_request


class TurnState(TypedDict, total=False):
    text: str
    turn: int
    request: dict
    result: dict


def run_turn(session, text, turn):
    def route(state):
        return {"request": route_request(state["text"], session.workspace).to_dict()}

    def dispatch(state):
        return {"result": session.dispatch(state["request"], state["turn"])}

    builder = StateGraph(TurnState)
    builder.add_node("route_task", route)
    builder.add_node("dispatch_task", dispatch)
    builder.add_edge(START, "route_task")
    builder.add_edge("route_task", "dispatch_task")
    builder.add_edge("dispatch_task", END)
    with SqliteSaver.from_conn_string(str(session.folder/"general_graph.sqlite")) as saver:
        graph = builder.compile(checkpointer=saver)
        result = graph.invoke({"text": text, "turn": turn},
            {"configurable": {"thread_id": session.meta["id"]}, "recursion_limit": 16})
    return result["result"]
