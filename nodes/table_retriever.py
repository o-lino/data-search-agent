"""
Table Retriever Node

Retrieves candidate tables from the catalog using:
1. Semantic search (RAG with embeddings)
2. Historical decision lookup
3. Keyword matching fallback
"""

from typing import Any

from ..state import AgentState, TableCandidate, HistoricalDecision
from ..rag.retriever import get_retriever
from ..memory.long_term import get_historical_decisions


async def retrieve_tables(state: AgentState) -> dict[str, Any]:
    """
    Node: Retrieve candidate tables from catalog.
    
    This node:
    1. Uses RAG to find semantically similar tables
    2. Looks up historical decisions for the concept
    3. Combines results and deduplicates
    
    Returns:
        State updates with candidate_tables and historical_decisions.
    """
    retriever = get_retriever()
    
    # 1. Semantic search using embedding query
    try:
        semantic_results = await retriever.search(
            query=state["embedding_query"],
            domain_filter=state["domain_hints"][0] if state["domain_hints"] else None,
            max_results=state["max_results"] * 2  # Get more for filtering
        )
    except Exception as e:
        # Fallback to empty if RAG fails
        print(f"Warning: RAG search failed: {e}")
        semantic_results = []
    
    # 2. Get historical decisions for this concept
    try:
        historical = await get_historical_decisions(
            concept_hash=state["concept_hash"],
            limit=10
        )
    except Exception as e:
        print(f"Warning: Historical lookup failed: {e}")
        historical = []
    
    # 3. Convert to typed models
    candidate_tables = []
    seen_ids = set()
    
    for result in semantic_results:
        table_id = result.get("id")
        if table_id and table_id not in seen_ids:
            seen_ids.add(table_id)
            candidate_tables.append(TableCandidate(
                id=table_id,
                name=result.get("name", ""),
                display_name=result.get("display_name", result.get("name", "")),
                description=result.get("description"),
                domain=result.get("domain"),
                schema_name=result.get("schema_name"),
                keywords=result.get("keywords", []),
                columns=result.get("columns", []),
                owner_id=result.get("owner_id"),
                owner_name=result.get("owner_name"),
            ))
    
    historical_decisions = [
        HistoricalDecision(
            concept_hash=h.get("concept_hash", state["concept_hash"]),
            table_id=h.get("table_id"),
            approved_count=h.get("approved_count", 0),
            rejected_count=h.get("rejected_count", 0),
            last_used_at=h.get("last_used_at"),
        )
        for h in historical
        if h.get("table_id")
    ]
    
    return {
        "candidate_tables": candidate_tables,
        "historical_decisions": historical_decisions,
        "current_step": "retrieved",
        "needs_more_context": len(candidate_tables) == 0,
    }
