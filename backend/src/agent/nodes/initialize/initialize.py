import anthropic
import datetime
from dotenv import load_dotenv
import os

from ..state import GraphState
from ..container import PersistentDockerRunner


load_dotenv()

if os.getenv("ANTHROPIC_API_KEY") is None:
    raise ValueError("ANTHROPIC_API_KEY is not set")


def initialize(state: GraphState) -> GraphState:
    """Initialize the analysis process"""
    try:
        runner = PersistentDockerRunner()
        runner.start()
        runner.verify_uploaded_files()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        return {
            "stock_symbol": state["stock_symbol"],
            "runner": runner,
            "timestamp": timestamp,
            "think_count": 0,
            # LLM Client
            "anthropic_client": anthropic_client,
            # Solution tracking
            "solutions": [],
            "processed_solutions": [],
            "best_solution": 0,
        }
    except Exception as e:
        print(f"Error starting Docker runner: {e}")
        raise RuntimeError(
            "Failed to initialize Docker runner. Ensure Docker is running and accessible."
        )
