from langgraph.graph import StateGraph, END
from nodes import GraphState, initialize, think, implement, aggregate, finish


def route_after_aggregate(state: GraphState) -> str:
    """Route based on think count and success rate"""
    success_rate = state.get("aggregate_metrics", {}).get("success_rate", 0)

    # Continue thinking if we haven't reached max iterations and success rate is low
    if state["think_count"] < 3 and (success_rate < 0.8 or state["think_count"] == 1):
        return "think"
    else:
        return "finish"


def create_parallel_stock_analysis_graph():
    """Create the LangGraph workflow with parallel solution processing"""

    workflow = StateGraph(GraphState)

    # Add nodes
    workflow.add_node("initialize", initialize)
    workflow.add_node("think", think)
    workflow.add_node("implement", implement)
    workflow.add_node("aggregate", aggregate)
    workflow.add_node("finish", finish)

    # Set entry point
    workflow.set_entry_point("initialize")

    # Add edges
    workflow.add_edge("initialize", "think")
    workflow.add_edge("think", "implement")
    workflow.add_edge("implement", "aggregate")

    # Conditional routing after aggregation
    workflow.add_conditional_edges(
        "aggregate",
        route_after_aggregate,
        {"think": "think", "finish": "finish"},
    )

    workflow.add_edge("finish", END)

    # graph = workflow.compile(name="invest-agent")
    return workflow.compile()


# Usage example
def run_parallel_stock_analysis(stock_symbol: str):
    """Run the parallel stock analysis workflow"""

    app = create_parallel_stock_analysis_graph()

    initial_state = {
        "stock_symbol": stock_symbol,
        "think_count": 0,
        "solutions": [],
    }

    final_state = app.invoke(initial_state)
    return final_state


# Example usage
if __name__ == "__main__":
    result = run_parallel_stock_analysis("QQQ")
    print(f"Analysis complete for {result['stock_symbol']}")
