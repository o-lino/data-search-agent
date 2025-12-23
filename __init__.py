"""
Table Search Agent

LangGraph-based intelligent agent for table search with:
- Hierarchical search (Domain → Owner → Table)
- Column-level search
- Disambiguation scoring
- Ambiguity detection
- LLM reranking
- Feedback learning
"""

from .graph import get_agent, create_agent, build_graph
from .state import (
    AgentState,
    create_initial_state,
    OutputMode,
    DataExistence,
    DomainInfo,
    OwnerInfo,
    TableInfo,
    TableMatch,
    CanonicalIntent,
    SingleMatchOutput,
    RankingOutput,
)

__all__ = [
    # Graph
    "get_agent",
    "create_agent",
    "build_graph",
    # State
    "AgentState",
    "create_initial_state",
    "OutputMode",
    "DataExistence",
    "DomainInfo",
    "OwnerInfo",
    "TableInfo",
    "TableMatch",
    "CanonicalIntent",
    "SingleMatchOutput",
    "RankingOutput",
]

__version__ = "2.0.0"
