"""
Column Search Node

Searches for tables based on column/field names.
Useful when users ask "where is the CPF field?" or "table with CNPJ".
"""

from typing import Any

from ..state import AgentState, TableMatch, TableInfo
from ..rag.column_retriever import get_column_retriever, ColumnSearchResult


async def search_by_columns(state: AgentState) -> dict[str, Any]:
    """
    Node: Search for tables based on column names.
    
    This is an alternative/complementary search that finds tables
    containing specific fields mentioned in the query.
    
    Example:
        Query: "onde tem o campo CPF?"
        Result: tb_clientes (has column nr_cpf)
    """
    intent = state.get("canonical_intent")
    context = state.get("context", {})
    raw_query = state.get("raw_query", "")
    
    # Determine search query
    # Look for field-specific keywords
    field_keywords = ["campo", "coluna", "atributo", "variável", "field"]
    is_column_search = any(kw in raw_query.lower() for kw in field_keywords)
    
    if not is_column_search and intent:
        # Check if intent suggests column search
        if intent.target_entity in ["cpf", "cnpj", "campo", "coluna"]:
            is_column_search = True
    
    # If not a column-specific query, return empty
    if not is_column_search:
        return {
            "column_search_results": [],
            "current_step": "column_search_skipped",
        }
    
    # Extract search term
    search_term = raw_query
    for kw in field_keywords:
        search_term = search_term.replace(kw, "").strip()
    
    # Also use data_need if available
    if intent and intent.data_need:
        search_term = intent.data_need
    
    retriever = get_column_retriever()
    
    try:
        results = await retriever.search(
            query=search_term,
            domain_filter=context.get("domain"),
            max_results=10,
        )
    except Exception as e:
        print(f"Warning: Column search failed: {e}")
        results = []
    
    # Convert to table matches grouped by table
    table_scores = {}
    
    for col_result in results:
        table_id = col_result.table_id
        
        if table_id not in table_scores:
            table_scores[table_id] = {
                "table_info": _build_table_info_from_column(col_result),
                "columns": [],
                "best_score": 0.0,
            }
        
        table_scores[table_id]["columns"].append(col_result.column_display_name)
        table_scores[table_id]["best_score"] = max(
            table_scores[table_id]["best_score"],
            col_result.similarity_score
        )
    
    # Create TableMatch for each unique table
    column_matches = []
    for table_id, data in table_scores.items():
        column_matches.append(TableMatch(
            table=data["table_info"],
            score=data["best_score"],
            semantic_score=data["best_score"],
            historical_score=0.5,
            context_score=0.0,
            certification_score=0.5,
            freshness_score=0.5,
            quality_score=0.5,
            reasoning=f"Contém campos: {', '.join(data['columns'][:3])}",
            matched_entities=data["columns"],
            is_double_certified=False,
            has_product_match=False,
        ))
    
    # Sort by score
    column_matches.sort(key=lambda x: x.score, reverse=True)
    
    return {
        "column_search_results": column_matches,
        "current_step": "column_search_complete",
    }


def _build_table_info_from_column(col: ColumnSearchResult) -> TableInfo:
    """Build TableInfo from column search result."""
    return TableInfo(
        id=col.table_id,
        name=col.table_name,
        display_name=col.table_display_name,
        summary=f"Tabela com campo {col.column_display_name}",
        domain_id=col.domain,
        domain_name=col.domain,
        owner_id=col.owner_id,
        owner_name=col.owner_name,
        keywords=[col.column_name, col.column_display_name],
    )


async def merge_column_and_table_results(state: AgentState) -> dict[str, Any]:
    """
    Merge results from column search and table search.
    
    Column matches get a boost if they directly answer the query.
    """
    table_matches = state.get("matched_tables", [])
    column_matches = state.get("column_search_results", [])
    
    if not column_matches:
        return {"current_step": "merge_complete"}
    
    # Merge: column results boost matching tables
    merged = {}
    
    # Start with table matches
    for tm in table_matches:
        merged[tm.table.id] = tm
    
    # Add/boost with column matches
    for cm in column_matches:
        table_id = cm.table.id
        
        if table_id in merged:
            # Boost existing match
            existing = merged[table_id]
            existing.score = min(1.0, existing.score + 0.15)  # Column match boost
            existing.reasoning += f" | ✓ Campo match: {cm.reasoning}"
        else:
            # Add new match from column search
            merged[table_id] = cm
    
    # Sort by score
    final_matches = sorted(merged.values(), key=lambda x: x.score, reverse=True)
    
    return {
        "matched_tables": list(final_matches)[:10],
        "current_step": "merge_complete",
    }
