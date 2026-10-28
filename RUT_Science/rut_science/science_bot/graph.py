"""Native LangGraph with durable SQLite checkpoints and confirmation interrupts.

Graph state holds references; environment.json is the scientific ledger authority.
Replayed dispatch calls use the same observation/action idempotency key.
"""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.sqlite import SqliteSaver


class GraphState(TypedDict, total=False):
    session_ref: str
    version: int
    steps: int


def build_graph(session, saver, max_steps=None):
    def confirm(state):
        if session.meta["confirmed"] != session.confirmation:
            supplied = interrupt({"draft_hash": session.confirmation, "spec": session.spec.to_dict()})
            session.confirm(supplied)
        return {"session_ref": session.meta["id"]}

    def propose(state):
        session.propose()
        return {}

    def observe(state):
        return {"version": session.env.state["version"]}

    def dispatch(state):
        # If graph checkpoint lags the ledger after a crash, skip the committed step.
        if state.get("version") == session.env.state["version"] and not session.env.done:
            session.step()
        return {"steps": state.get("steps", 0)+1}

    def route(state):
        if session.env.done:
            return "finish"
        if session.cancel_requested.is_set():
            session.env.state["phase"] = "cancelled"
            session.meta["phase"] = "cancelled"; session.save()
            return END
        if session.pause_requested.is_set() or (max_steps is not None and state.get("steps", 0) >= max_steps):
            session.meta["phase"] = "paused"; session.save()
            return END
        return "dispatch"

    def finish(state):
        session.finish()
        return {}

    g = StateGraph(GraphState)
    for name, node in (("await_confirmation", confirm), ("propose", propose), ("observe", observe),
                       ("dispatch", dispatch), ("finish", finish)):
        g.add_node(name, node)
    g.add_edge(START, "await_confirmation")
    g.add_edge("await_confirmation", "propose")
    g.add_edge("propose", "observe")
    g.add_conditional_edges("observe", route)
    g.add_edge("dispatch", "observe")
    g.add_edge("finish", END)
    return g.compile(checkpointer=saver)


def run_graph(session, max_steps=None):
    config = {"configurable": {"thread_id": session.meta["id"]}, "recursion_limit": 128}
    with SqliteSaver.from_conn_string(str(session.folder/"graph.sqlite")) as saver:
        graph = build_graph(session, saver, max_steps)
        previous = graph.get_state(config)
        if previous.tasks and any(t.interrupts for t in previous.tasks):
            graph.invoke(Command(resume=session.confirmation), config)
        else:
            graph.invoke({"session_ref": session.meta["id"], "steps": 0}, config)
