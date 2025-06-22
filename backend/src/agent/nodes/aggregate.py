from .state import GraphState


def aggregate(state: GraphState) -> GraphState:
    """Aggregate all processed solutions and decide next step"""
    solutions = state["solutions"]
    next_iteration = []

    for index, s in enumerate(solutions[-1]):
        solution_id = f'{state["think_count"]+1}_{index+1}'

        if not s.get("result"):
            continue

        if (
            s["pre_result"].get("final_value")
            and s["result"].get("final_value")
            and s["pre_result"].get("final_value") < s["result"].get("final_value")
        ):
            next_iteration.append(
                {
                    "solution_id": solution_id,
                    "description": "",
                    "pre_description": s.get("pre_description", ""),
                    "code": "",
                    "result": "",
                    "improvement": "",
                    "pre_result": s.get("pre_result", ""),
                    "pre_code": s.get("pre_code", ""),
                }
            )
        else:
            next_iteration.append(
                {
                    "solution_id": solution_id,
                    "description": "",
                    "pre_description": s.get("description", ""),
                    "code": "",
                    "result": "",
                    "improvement": "",
                    "pre_result": s.get("result", ""),
                    "previous_code": s.get("code", ""),
                }
            )

    length = max(1, len(solutions[-1]) // 2)
    next_iteration = sorted(
        next_iteration,
        key=lambda s: s["pre_result"].get("final_value", 0),
        reverse=True,
    )[:length]

    state["solutions"].append(next_iteration)

    return {
        **state,
    }
