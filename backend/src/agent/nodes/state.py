from __future__ import annotations
from dataclasses import dataclass, field
from typing import TypedDict
from langgraph.graph import add_messages
from typing_extensions import Annotated
import operator


# ====================================== #
from typing import TypedDict, List, Dict, Any, Annotated, Union
import operator
from .container.container import PersistentDockerRunner
from anthropic import Anthropic


class Solution(TypedDict):
    solution_id: str
    pre_description: str
    description: str
    improvement: str
    pre_code: str
    code: str
    pre_result: Dict[str, Any]
    result: Dict
    


class GraphState(TypedDict):
    """Main state that flows through the graph"""

    stock_symbol: str
    runner: Union[PersistentDockerRunner]
    timestamp: str
    think_count: int

    # LLM Client
    anthropic_client: Anthropic

    # Solution
    solutions: List[List[Solution]]


# ====================================== #


class OverallState(TypedDict):
    messages: Annotated[list, add_messages]
    search_query: Annotated[list, operator.add]
    web_research_result: Annotated[list, operator.add]
    sources_gathered: Annotated[list, operator.add]
    initial_search_query_count: int
    max_research_loops: int
    research_loop_count: int
    reasoning_model: str


class ReflectionState(TypedDict):
    is_sufficient: bool
    knowledge_gap: str
    follow_up_queries: Annotated[list, operator.add]
    research_loop_count: int
    number_of_ran_queries: int


class Query(TypedDict):
    query: str
    rationale: str


class QueryGenerationState(TypedDict):
    search_query: list[Query]


class WebSearchState(TypedDict):
    search_query: str
    id: str


@dataclass(kw_only=True)
class SearchStateOutput:
    running_summary: str = field(default=None)  # Final report
