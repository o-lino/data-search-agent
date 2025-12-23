"""
Disambiguation Search Node

Applies multi-dimensional scoring to table candidates.
Combines semantic search with certification, freshness, quality, and historical learning.
"""

from typing import Any
from datetime import datetime

from ..state import AgentState, TableMatch, TableInfo, DataExistence
from ..disambiguation import (
    calculate_disambiguation_score,
    TableMetadataForScoring,
)
from ..disambiguation.historical_scorer import (
    get_historical_score_for_table,
    get_historically_approved_tables,
)
from ..rag.retriever import get_retriever


async def search_tables_with_disambiguation(state: AgentState) -> dict[str, Any]:
    """
    Node: Search tables with full disambiguation scoring.
    
    V4 Flow:
    1. Get historically approved tables for this intent
    2. Semantic search (RAG) for initial candidates
    3. Apply disambiguation scoring (cert, fresh, quality, context)
    4. Add historical learning score
    5. Combine all scores with use-case weights
    6. Return ranked results
    """
    intent = state.get("canonical_intent")
    matched_owners = state.get("matched_owners", [])
    context = state.get("context", {})
    
    # Determine use case
    use_case = context.get("use_case", "default")
    user_product = context.get("produto") or (intent.target_product if intent else None)
    user_domain = None
    if state.get("matched_domains"):
        user_domain = state["matched_domains"][0].domain.name
    
    retriever = get_retriever()
    
    # V4: Get historically approved tables for this intent
    historical_boosts = {}
    if intent:
        try:
            historical_tables = await get_historically_approved_tables(intent, limit=10)
            for h in historical_tables:
                historical_boosts[h["table_id"]] = h["approval_rate"]
        except Exception as e:
            print(f"Warning: Historical lookup failed: {e}")
    
    # Build search query from intent
    query_parts = []
    if intent:
        query_parts.append(intent.data_need or "")
        if intent.target_entity:
            query_parts.append(f"entidade: {intent.target_entity}")
        if intent.target_product:
            query_parts.append(f"produto: {intent.target_product}")
        if intent.target_segment:
            query_parts.append(f"segmento: {intent.target_segment}")
        if intent.granularity:
            query_parts.append(f"granularidade: {intent.granularity}")
    
    search_query = " | ".join(filter(None, query_parts)) or state.get("raw_query", "")
    
    # Semantic search
    try:
        raw_results = await retriever.search(
            query=search_query,
            domain_filter=user_domain,
            max_results=20,
        )
    except Exception as e:
        print(f"Warning: RAG search failed: {e}")
        raw_results = []
    
    # Apply disambiguation scoring to each result
    owner_ids = {o.owner.id for o in matched_owners}
    table_matches = []
    
    for result in raw_results:
        table_id = result.get("id")
        
        # Build TableInfo
        table_info = TableInfo(
            id=table_id,
            name=result.get("name", ""),
            display_name=result.get("display_name", result.get("name", "")),
            summary=result.get("description", "")[:200],
            domain_id=result.get("domain", ""),
            domain_name=result.get("domain", ""),
            owner_id=result.get("owner_id") or 0,
            owner_name=result.get("owner_name", ""),
            keywords=result.get("keywords", []),
            data_layer=result.get("data_layer"),
            is_golden_source=result.get("is_golden_source", False),
            is_visao_cliente=result.get("is_visao_cliente", False),
            update_frequency=result.get("update_frequency"),
            inferred_product=result.get("inferred_product"),
        )
        
        # Create metadata for scoring
        metadata = TableMetadataForScoring(
            table_name=table_info.name,
            data_layer=table_info.data_layer,
            is_golden_source=table_info.is_golden_source,
            is_visao_cliente=table_info.is_visao_cliente,
            domain=table_info.domain_name,
            update_frequency=table_info.update_frequency,
            last_updated=datetime.fromisoformat(result["last_updated"]) if result.get("last_updated") else None,
            inferred_product=table_info.inferred_product,
        )
        
        # Calculate disambiguation score
        disamb_score = calculate_disambiguation_score(
            table=metadata,
            use_case=use_case,
            user_domain=user_domain,
            user_product=user_product,
        )
        
        # Base semantic score
        semantic_score = 1.0 - result.get("_distance", 0.5)
        
        # V4: Historical score from feedback learning
        historical_score = historical_boosts.get(table_id, 0.5)
        if historical_score == 0.5 and intent:
            # Try individual lookup if not in batch
            try:
                hist_score, is_reliable = await get_historical_score_for_table(intent, table_id)
                if is_reliable:
                    historical_score = hist_score
            except:
                pass
        
        # Owner boost
        owner_boost = 0.1 if table_info.owner_id in owner_ids else 0.0
        
        # V4: Combined score with historical learning
        # semantic (25%) + disambiguation (50%) + historical (15%) + owner (10%)
        combined_score = (
            semantic_score * 0.25 +
            disamb_score.total_score * 0.50 +
            historical_score * 0.15 +
            owner_boost * 0.10
        )
        
        # Build reasoning with historical info
        reasoning = disamb_score.reasoning
        if historical_score > 0.7:
            reasoning += f" | ✓ Histórico: {historical_score:.0%} aprovações"
        elif historical_score < 0.3:
            reasoning += f" | ⚠️ Histórico: {historical_score:.0%} aprovações"
        
        table_matches.append(TableMatch(
            table=table_info,
            score=combined_score,
            semantic_score=semantic_score,
            historical_score=historical_score,
            context_score=disamb_score.context_score,
            certification_score=disamb_score.certification_score,
            freshness_score=disamb_score.freshness_score,
            quality_score=disamb_score.quality_score,
            reasoning=reasoning,
            matched_entities=table_info.main_entities,
            is_double_certified=disamb_score.is_double_certified,
            has_product_match=disamb_score.has_product_match,
        ))
    
    # Sort by combined score
    table_matches.sort(key=lambda x: x.score, reverse=True)
    
    # Determine data existence
    data_existence = DataExistence.UNCERTAIN
    if table_matches and table_matches[0].score >= 0.60:
        data_existence = DataExistence.EXISTS
    elif not table_matches or table_matches[0].score < 0.30:
        data_existence = DataExistence.NEEDS_CREATION
    
    return {
        "matched_tables": table_matches[:10],
        "data_existence": data_existence,
        "current_step": "tables_searched",
    }

