from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from .state import GraphState, Solution
import json


improve_strategy_code_prompt = """
You are a professional quantitative engineer. Your objective is to enhance an existing trading strategy for the QQQ ETF using 15-minute bar data, with a specific focus on **maximizing the Sharpe Ratio**.

Based on the **Strategy Description** and the **Improvement to Apply**, generate updated code using the template provided. You must strictly follow the coding structure and only use the allowed libraries.

⚠️ **Important Instructions:**
- Only return **code**. Do **not** include any explanations, comments outside the template, or formatting beyond Python code.
- Follow the given **code template** structure.
- Use only the following libraries: `backtrader`, `pandas`, `numpy`, and standard Python libraries.

!!! Return the python code in a single code block with no additional text or formatting.
---
"""

code_template_prompt = """
## Code Template

- You can only use libraries `backtrader`, `pandas`, `numpy`, or libraries built-in in Python.
- The class must be named `MyStrategy`.
- The `__init__` method should not have any input parameters.

## Data Structure
Datetime,Open,High,Low,Close,Volume,StockName
2023-04-03 09:30:00,315.21,316.11,314.93,315.62,3038750,QQQ
2023-04-03 09:45:00,315.60,316.43,315.34,315.58,2423119,QQQ
2023-04-03 10:00:00,315.59,316.31,315.33,315.78,2384854,QQQ

```python
import backtrader as bt
import pandas as pd
import numpy as np
import math
import datetime


class MyStrategy(bt.Strategy):
    \"\"\"
    Template for a custom backtrader strategy.

    Steps to implement:
    - Define parameters in `params`
    - Initialize indicators/signals in `__init__`
    - Add entry/exit logic in `next`
    \"\"\"

    params = dict(
        # Define any strategy parameters here
        example_param=10,
    )

    def __init__(self):
        \"\"\"
        Called once at the start of the strategy.
        Use this to initialize indicators or other variables.
        Should not have any input parameters.
        \"\"\"
        pass  # TODO: Add indicators here (e.g., SMA, RSI)

    def next(self):
        \"\"\"
        Called on each new data point (bar).
        Add your trading logic here.
        \"\"\"
        pass  # TODO: Add entry/exit logic here
```
"""


class SolutionImplementer:
    """Handles individual solution processing"""

    def __init__(
        self,
        state: GraphState,
    ):
        self.stock_symbol = state["stock_symbol"]
        self.runner = state["runner"]
        self.anthropic_client = state["anthropic_client"]
        self.timestamp = state["timestamp"]

    def process_solution(self, solution: Solution) -> Solution:
        """Process a single solution through implement -> verify -> eval cycle"""
        solution_id = solution["solution_id"]
        retry_count = 0
        max_retries = 5

        print(f"\n============= strategy-{solution['solution_id']} =============")
        while retry_count <= max_retries:
            try:

                # Implement
                implementation_result = self._implement_solution(solution)

                # print(f"[Debug] Implementation Result: {implementation_result}")

                # Compile
                compile_passed = self._compile_solution(
                    implementation_result, solution_id
                )

                if compile_passed:
                    # Evaluate
                    evaluation_result = self._eval_solution(solution_id)

                    return {
                        **solution,
                        "code": implementation_result,
                        "result": evaluation_result,
                    }
                else:
                    retry_count += 1
                    if retry_count > max_retries:
                        return {
                            **solution,
                            "code": implementation_result,
                            "result": {},
                        }

            except Exception as e:
                print(f"❌ [Error] Processing strategy-{solution_id}")
                retry_count += 1
                if retry_count > max_retries:
                    return {}

    def _implement_solution(self, solution: Solution) -> Solution:
        """Implement a single solution"""
        print(f"\n[Implement]", f"strategy-{solution['solution_id']}")
        # print(f"[Debug]\n", solution)

        prompt = improve_strategy_code_prompt
        if solution.get("description"):
            prompt += f"## Strategy Description\n{solution['description']}\n\n"
        if solution.get("improvement"):
            prompt += f"## Improvement to Apply\n{solution['improvement']}\n\n"
        if solution.get("pre_code"):
            prompt += (
                f"## Previous Code\n```python\n{solution['pre_code']}\n```\n\n"
            )
        prompt += code_template_prompt

        # print(f"[Debug][Implement] Prompt for LLM: {prompt}")

        response = self.anthropic_client.messages.create(
            model="claude-opus-4-20250514",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )

        # print(f"[Debug][Implement] Response from LLM: {response}")

        if not response or not response.content:
            raise ValueError("No response from LLM or empty content")

        implementation_code = response.content[0].text.strip()
        # remove ```json and ``` from the output
        if implementation_code.startswith("```python"):
            implementation_code = implementation_code[9:].strip()
        if implementation_code.endswith("```"):
            implementation_code = implementation_code[:-3].strip()

        implementation_code = implementation_code.strip()

        print(f"✅ [Implement] strategy-{solution['solution_id']}")

        return implementation_code

    def _compile_solution(self, implementation: str, solution_id) -> bool:
        """Compile a single solution implementation"""
        print(f"[Compile] strategy-{solution_id}")
        max_retries = 5
        retry_count = 0
        while retry_count < max_retries:
            try:
                result = self.runner.upload_file(
                    implementation, f"strategies/strategy-{solution_id}.py"
                )
                if not result:
                    raise ValueError("Failed to upload implementation code")

                # compile the python code in the container
                output = self.runner.run_command(
                    f"python -m py_compile strategies/strategy-{solution_id}.py"
                )
                if "SyntaxError" in output or "IndentationError" in output:
                    print(f"❌ [Compile Error] ", solution_id)
                    return False
                print(f"✅ [Compile] strategy-{solution_id}")
                return True
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    print(
                        f"Failed to compile solution {solution_id} after {max_retries} retries"
                    )
                    return False
        return False

    def _eval_solution(self, solution_id: str) -> Dict[str, Any]:
        """Evaluate a single verified solution"""
        print(f"[Evaluate] strategy-{solution_id}")

        res = self.runner.run_command(
            f"python metrics.py --strategy-path strategies/strategy-{solution_id}.py --result-path logs/res-{solution_id}.json"
        )

        print(f"✅ [Evaluate] strategy-{solution_id}: \n{res}\n")

        # download the result file
        result_content = self.runner.download_file(f"logs/res-{solution_id}.json")
        if not result_content:
            raise ValueError(f"Failed to download evaluation result for {solution_id}")

        json_data = result_content.strip()
        if not json_data:
            raise ValueError(f"Evaluation result for {solution_id} is empty")

        # Parse the JSON result
        try:
            evaluation_result = json.loads(json_data)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON format in evaluation result for {solution_id}: {e}"
            )

        return evaluation_result


def implement(state: GraphState) -> GraphState:
    """Process all solutions in parallel"""
    if not state["solutions"]:
        return state

    processor = SolutionImplementer(state)

    # Process solutions in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(len(state["solutions"]), 5)) as executor:
        # Submit all solutions for processing
        future_to_solution = {
            executor.submit(processor.process_solution, solution): (solution)
            for solution in state["solutions"][-1]
        }

        # Collect results as they complete
        updated_solutions = []
        for future in as_completed(future_to_solution):
            try:
                result = future.result()
                if result is None:
                    continue  # Skip if processing failed
                # print(result)
                updated_solutions.append(result)
            except Exception as e:
                print(f"❌ [Implement Error] {e}")
                continue
    state["solutions"][-1] = updated_solutions
    return {**state}
