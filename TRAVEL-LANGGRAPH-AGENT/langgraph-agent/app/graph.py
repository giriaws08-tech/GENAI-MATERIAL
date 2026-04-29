from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .nodes import (
    input_processor_node,
    flight_agent,
    hotel_agent,
    activity_agent,
    supervisor_node,
    budget_warning_node,
    should_continue
)

from state import TravelState

builder = StateGraph(TravelState)

builder.add_node("processor", input_processor_node)
builder.add_node("flights", flight_agent)
builder.add_node("hotels", hotel_agent)
builder.add_node("activities", activity_agent)
builder.add_node("supervisor", supervisor_node)
builder.add_node("budget_warning", budget_warning_node)

builder.add_conditional_edges(
    "supervisor",
    should_continue,
    {
        "warn": "budget_warning",
        "continue": "activities"
    }
)

builder.set_entry_point("processor")

builder.add_edge("processor", "flights")
builder.add_edge("flights", "hotels")
builder.add_edge("hotels", "activities")
builder.add_edge("activities", "supervisor")

builder.add_edge("supervisor", END)
builder.add_edge("budget_warning", END)

memory = MemorySaver()

graph = builder.compile(checkpointer=memory)