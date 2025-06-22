from .state import GraphState


def finish(state: GraphState) -> GraphState:
    """Final processing and output"""
    print("[Finish] Finalizing the workflow...")

    if len(state["solutions"][-1]) == 0:
        print("[Finish] No solutions found. Exiting.")
        return state

    last_iteration = state["solutions"][-1]
    
    best_solution = sorted(
        last_iteration, key=lambda s: ({} if not s.get("result") else s.get("result")).get("final_value", 0)
    )[-1]

    print(f"[Finish] Best solution: {best_solution['solution_id']}")
    print(
        f"[Finish] Best solution value: {best_solution.get('result', {}).get('final_value', 0)}"
    )

    runner = state["runner"]
    if runner:
        try:
            runner.stop()
        except Exception as e:
            print(f"Error stopping Docker runner: {e}")

    return {
        **state,
    }
