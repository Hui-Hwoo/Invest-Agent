from .state import GraphState
import json

initial_prompt = """
You are a professional quantitative engineer. Your task is to develop innovative trading strategies for the QQQ ETF using 15-minute bar data. Your primary objective is to maximize the Sharpe Ratio.

Please draw on your full expertise and knowledge—be bold, creative, and avoid conventional or overly simplistic ideas. I want **four distinct and imaginative strategy directions** that go beyond the basics.

Output your response **strictly** in JSON format—**no additional explanations or commentary**.

Start your JSON list with the following format:

```json
{{
    "strategies": [
  "# Strategy 1: <brief creative title and description>",
  "# Strategy 2: <brief creative title and description>",
  "# Strategy 3: <brief creative title and description>"
  "# Strategy 4: <brief creative title and description>"
]
}}
```

This version:
- Uses clear professional tone and grammar.
- Emphasizes the *creative*, *non-boring* nature of the request.
- Reinforces the JSON-only output constraint.
- Structures the expected output with a helpful example header.

# Example Output:
```json
{{
    "strategies": [
  "# Strategy 1: Trend-Following with ADX Confirmation — This strategy takes long-only positions when short-term momentum aligns with strong trend strength. Specifically, it enters a long trade when the 20-period simple moving average (SMA) crosses above the 150-period SMA, signaling bullish momentum, and the 14-period Average Directional Index (ADX) is above 20, confirming a strong trend. The position is exited when either the SMA crossover reverses or the ADX drops below 20. Signals are generated on bar close and executed on the following bar.",
  "# Strategy 2: Multi-Factor Sentiment Analysis",
  "# Strategy 3: Adaptive Volatility-Based Position Sizing"
  "# Strategy 4: Alternative Data-Driven Reversal Strategy"
]
}}
"""


improve_strategy_prompt = """
You are a professional quantitative engineer. Your objective is to enhance an existing trading strategy for the QQQ ETF using 15-minute bar data, with a specific focus on **maximizing the Sharpe Ratio**.

Your task is to **critically evaluate** the provided strategy and identify **concrete areas for improvement**. Use your expertise to suggest refined or alternative components—such as entry/exit logic, technical indicators, filters, risk management, or position sizing—that can measurably improve performance.

** Output your response **strictly** in JSON format—**no additional explanations or commentary**. 

This is an **iterative optimization process**. In the improvement, You must:
- Pinpoint weaknesses or inefficiencies in the current strategy.
- Explain how these aspects may be limiting the Sharpe Ratio.
- Propose a **revised, improved version** of the strategy.
- Provide updated implementation logic or pseudocode, if applicable.

Avoid vague or generic advice—your suggestions should be **precise, creative, and actionable**, backed by clear reasoning.

### Output Format

Just return the output in JSON format with the following structure:

```json
{{
  "description": "Concise but clear explanation of the updated strategy and what has changed.",
  "improvement": "Detailed explanation of what was improved, why it matters, and how it addresses the original strategy's weaknesses."
}}
```
---

You will be given the previous strategy, its implementation, and the resulting performance metrics.

### Previous Strategy
{description}

### Previous Code
{code}

### Previous Result
{result}

---


"""


def think(state: GraphState) -> GraphState:
    """Generate multiple solutions for stock analysis"""

    anthropic_client = state["anthropic_client"]

    max_retries = 3  # Maximum number of retries for LLM calls
    retry_count = 0

    if state["think_count"] == 0:
        while retry_count < max_retries:
            try:
                # Generate initial solutions using the LLM
                message = anthropic_client.messages.create(
                    model="claude-opus-4-20250514",
                    max_tokens=8192,
                    messages=[{"role": "user", "content": initial_prompt}],
                )
                solution_string = message.content[0].text.strip()
                # remove ```json and ``` from the output
                if solution_string.startswith("```json"):
                    solution_string = solution_string[7:].strip()
                if solution_string.endswith("```"):
                    solution_string = solution_string[:-3].strip()

                # print(f"[Debug] \n{solution_string.strip()}\n")
                solutions = json.loads(solution_string.strip()).get("strategies", [])
                break  # Exit loop if successful
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    raise ValueError(
                        "Failed to generate solutions after multiple retries"
                    ) from e
                # retry on any error
                print(f"❌ [First Think] Error generating solutions: {e}")
                continue

        previous_solutions = state["solutions"]
        new_solutions = []
        for index, solution in enumerate(solutions):
            new_solutions.append(
                {
                    "solution_id": f"{state['think_count']+1}_{index+1}",
                    "description": solution.strip(),
                    "pre_description": "",
                    "code": "",
                    "pre_code": "",
                    "result": {},
                    "pre_result": {},
                    "improvement": "",
                }
            )

        return {
            **state,
            "think_count": state["think_count"] + 1,
            "solutions": previous_solutions + [new_solutions],
        }
    else:
        previous_strategies = state["solutions"][-1]
        updated_strategies = []
        for index, old_strategy in enumerate(previous_strategies):
            finished = False

            max_retries = 5  # Maximum number of retries for LLM calls
            retry_count = 0

            while not finished and retry_count < max_retries:
                try:
                    prompt = improve_strategy_prompt.format(
                        description=old_strategy.get("pre_description", ""),
                        code=old_strategy.get("pre_code", ""),
                        result=old_strategy.get("pre_result", ""),
                    )
                    message = anthropic_client.messages.create(
                        model="claude-opus-4-20250514",
                        max_tokens=8192,
                        messages=[{"role": "user", "content": prompt}],
                    )

                    solution_string = message.content[0].text.strip()

                    # remove ```json and ``` from the output
                    if solution_string.startswith("```json"):
                        solution_string = solution_string[7:].strip()
                    if solution_string.endswith("```"):
                        solution_string = solution_string[:-3].strip()

                    # print(f"[Debug][Think] Prompt for LLM: {solution_string}")

                    # print(f"[Debug] \n{solution_string.strip()}\n")
                    response = json.loads(solution_string.strip())
                    # print(f"[Debug] Response from LLM: {response}")

                    if (
                        not isinstance(response, dict)
                        or "description" not in response
                        or "improvement" not in response
                    ):
                        raise ValueError("Invalid response format")

                    old_strategy["description"] = response.get("description")
                    old_strategy["improvement"] = response.get("improvement")
                    updated_strategies.append(old_strategy)

                    finished = True  # Exit loop if successful
                except Exception as e:
                    # retry on any error
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise ValueError(
                            "Failed to generate updated strategy after multiple retries"
                        ) from e
                    print(f"❌ [Think] Error generating solutions: {e}")
                    continue

        previous_solutions = state["solutions"]
        previous_solutions[-1] = updated_strategies

        return {
            **state,
            "think_count": state["think_count"] + 1,
            "solutions": previous_solutions,
        }
