"""
LangGraph Workflow

Table Search Agent workflow with:
- Hierarchical search (Domain → Owner → Table)
- Column-level search
- Disambiguation scoring
- Ambiguity detection
- LLM reranking (conditional)
"""

from typing import Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import AgentState


# ============== Node Imports ==============

async def normalize_intent(state: AgentState) -> dict[str, Any]:
    """Extract canonical intent from query."""
    from .nodes.intent_normalizer import normalize_intent as _normalize
    return await _normalize(state)


async def search_domains(state: AgentState) -> dict[str, Any]:
    """Search for relevant domains."""
    from .nodes.hierarchical_search import search_domains as _search
    return await _search(state)


async def search_owners(state: AgentState) -> dict[str, Any]:
    """Search for data owners."""
    from .nodes.hierarchical_search import search_owners as _search
    return await _search(state)


async def search_tables(state: AgentState) -> dict[str, Any]:
    """Search tables with disambiguation scoring."""
    from .nodes.disambiguation_search import search_tables_with_disambiguation
    return await search_tables_with_disambiguation(state)


async def search_columns(state: AgentState) -> dict[str, Any]:
    """Search by column names."""
    from .nodes.column_search import search_by_columns
    return await search_by_columns(state)


async def merge_results(state: AgentState) -> dict[str, Any]:
    """Merge table and column search results."""
    from .nodes.column_search import merge_column_and_table_results
    return await merge_column_and_table_results(state)


async def rerank(state: AgentState) -> dict[str, Any]:
    """LLM reranking when scores are close."""
    from .nodes.llm_reranker import llm_rerank_node
    return await llm_rerank_node(state)


async def check_ambiguity(state: AgentState) -> dict[str, Any]:
    """Detect ambiguity in results."""
    from .nodes.ambiguity_check import check_ambiguity as _check
    return await _check(state)


async def decide(state: AgentState) -> dict[str, Any]:
    """Build final decision."""
    from .nodes.decision_builder_v2 import decide_v2
    
    base = await decide_v2(state)
    
    # Add ambiguity info
    ambiguity = state.get("ambiguity_result")
    if ambiguity and hasattr(ambiguity, "is_ambiguous") and ambiguity.is_ambiguous:
        base["ambiguity"] = {
            "type": ambiguity.type.value,
            "is_ambiguous": True,
            "clarifying_question": ambiguity.clarifying_question,
            "options": [
                {"id": o.id, "label": o.label, "table_id": o.table_id}
                for o in ambiguity.options
            ],
        }
    else:
        base["ambiguity"] = {"type": "NONE", "is_ambiguous": False}
    
    base["llm_reranked"] = state.get("llm_reranked", False)
    return base


async def record_feedback(state: AgentState) -> dict[str, Any]:
    """Record decision for learning."""
    from .nodes.feedback_recorder_v2 import record_feedback_v2
    return await record_feedback_v2(state)


# ============== Graph Builder ==============

def build_graph() -> StateGraph:
    """
    Build agent workflow.
    
    Flow:
    START → intent → domains → owners → 
    → [tables + columns] → merge → rerank → 
    → ambiguity → decide → feedback → END
    """
    workflow = StateGraph(AgentState)
    
    # Nodes
    workflow.add_node("intent", normalize_intent)
    workflow.add_node("domains", search_domains)
    workflow.add_node("owners", search_owners)
    workflow.add_node("tables", search_tables)
    workflow.add_node("columns", search_columns)
    workflow.add_node("merge", merge_results)
    workflow.add_node("rerank", rerank)
    workflow.add_node("ambiguity", check_ambiguity)
    workflow.add_node("decide", decide)
    workflow.add_node("feedback", record_feedback)
    
    # Flow
    workflow.set_entry_point("intent")
    workflow.add_edge("intent", "domains")
    workflow.add_edge("domains", "owners")
    
    # Parallel search
    workflow.add_edge("owners", "tables")
    workflow.add_edge("owners", "columns")
    workflow.add_edge("tables", "merge")
    workflow.add_edge("columns", "merge")
    
    # Post-processing
    workflow.add_edge("merge", "rerank")
    workflow.add_edge("rerank", "ambiguity")
    workflow.add_edge("ambiguity", "decide")
    workflow.add_edge("decide", "feedback")
    workflow.add_edge("feedback", END)
    
    return workflow


# ============== Agent Factory ==============

_agent = None


def get_agent():
    """Get or create agent instance."""
    global _agent
    if _agent is None:
        memory = MemorySaver()
        _agent = build_graph().compile(checkpointer=memory)
    return _agent


def create_agent(with_memory: bool = True):
    """Create new agent instance."""
    workflow = build_graph()
    if with_memory:
        return workflow.compile(checkpointer=MemorySaver())
    return workflow.compile()

