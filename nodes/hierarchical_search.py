"""
Hierarchical Search Node

Performs 3-level search: Domain → Owner → Table
Uses canonical intent for more targeted queries.
"""

from typing import Any

from ..state import (
    AgentState, 
    DomainMatch, 
    OwnerMatch, 
    TableMatch,
    DataExistence,
)
from ..indexing.pipeline import get_pre_indexing_pipeline
from ..rag.retriever import get_retriever
from src.core.config import settings


async def search_domains(state: AgentState) -> dict[str, Any]:
    """
    Node: Search for matching domains.
    
    Uses inferred_domains from canonical intent
    plus keyword matching against domain registry.
    """
    intent = state.get("canonical_intent")
    if not intent:
        return {
            "matched_domains": [],
            "current_step": "domains_searched",
        }
    
    pipeline = get_pre_indexing_pipeline()
    
    # Collect keywords from intent
    keywords = []
    if intent.data_need:
        keywords.append(intent.data_need)
    if intent.target_entity:
        keywords.append(intent.target_entity)
    if intent.target_product:
        keywords.append(intent.target_product)
    if intent.target_segment:
        keywords.append(intent.target_segment)
    keywords.extend(intent.inferred_domains)
    
    # Search domains by keywords
    matching_domains = pipeline.get_domains_by_keywords(keywords)
    
    # Score domains
    domain_matches = []
    for domain in matching_domains:
        # Calculate overlap score
        domain_kw = set(k.lower() for k in domain.keywords)
        query_kw = set(k.lower() for k in keywords)
        overlap = len(domain_kw & query_kw)
        score = min(1.0, overlap / max(len(query_kw), 1) + 0.3)  # Boost
        
        domain_matches.append(DomainMatch(
            domain=domain,
            score=score,
            reasoning=f"Match por keywords: {', '.join(domain_kw & query_kw)}"
        ))
    
    # Sort by score
    domain_matches.sort(key=lambda x: x.score, reverse=True)
    
    # If no matches from keywords, use all domains (fallback)
    if not domain_matches:
        all_domains = list(pipeline._domains.values())
        domain_matches = [
            DomainMatch(domain=d, score=0.3, reasoning="Fallback: sem match direto")
            for d in all_domains[:5]
        ]
    
    return {
        "matched_domains": domain_matches[:5],
        "current_step": "domains_searched",
    }


async def search_owners(state: AgentState) -> dict[str, Any]:
    """
    Node: Search for owners within matched domains.
    
    Prioritizes owners from top-scoring domains.
    """
    pipeline = get_pre_indexing_pipeline()
    matched_domains = state.get("matched_domains", [])
    
    owner_matches = []
    seen_owners = set()
    
    # Get owners from each matched domain
    for domain_match in matched_domains:
        domain_owners = pipeline.get_owners_by_domain(domain_match.domain.id)
        
        for owner in domain_owners:
            if owner.id in seen_owners:
                continue
            seen_owners.add(owner.id)
            
            # Score combines domain score and owner's historical approval rate
            score = (domain_match.score * 0.6) + (owner.approval_rate * 0.4)
            
            owner_matches.append(OwnerMatch(
                owner=owner,
                score=score,
                reasoning=f"Domínio: {domain_match.domain.name} | Aprovação histórica: {owner.approval_rate:.0%}"
            ))
    
    # Sort by score
    owner_matches.sort(key=lambda x: x.score, reverse=True)
    
    return {
        "matched_owners": owner_matches[:10],
        "current_step": "owners_searched",
    }


async def search_tables_v2(state: AgentState) -> dict[str, Any]:
    """
    Node: Search for tables using RAG with summarized metadata.
    
    Uses canonical intent for targeted semantic search.
    Filters by matched domains/owners.
    """
    intent = state.get("canonical_intent")
    matched_owners = state.get("matched_owners", [])
    
    retriever = get_retriever()
    
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
    
    # Get domain filter from top matched domain
    domain_filter = None
    if state.get("matched_domains"):
        domain_filter = state["matched_domains"][0].domain.name
    
    # Semantic search
    try:
        raw_results = await retriever.search(
            query=search_query,
            domain_filter=domain_filter,
            max_results=20,
        )
    except Exception as e:
        print(f"Warning: RAG search failed: {e}")
        raw_results = []
    
    # Convert to TableMatch
    pipeline = get_pre_indexing_pipeline()
    owner_ids = {o.owner.id for o in matched_owners}
    
    table_matches = []
    for result in raw_results:
        table_id = result.get("id")
        table_info = pipeline.get_table(table_id)
        
        if not table_info:
            # Create from raw result
            from ..state import TableInfo
            table_info = TableInfo(
                id=table_id,
                name=result.get("name", ""),
                display_name=result.get("display_name", ""),
                summary=result.get("description", "")[:200],
                domain_id=result.get("domain", ""),
                domain_name=result.get("domain", ""),
                owner_id=result.get("owner_id") or 0,
                owner_name=result.get("owner_name", ""),
                keywords=result.get("keywords", []),
            )
        
        # Calculate score
        base_score = 1.0 - result.get("_distance", 0.5)  # Distance to similarity
        
        # Boost if owner is in our matched owners
        owner_boost = 0.2 if table_info.owner_id in owner_ids else 0.0
        
        # Context score from intent matching
        context_score = _calculate_context_score(intent, table_info)
        
        total_score = (base_score * 0.5) + (owner_boost * 0.3) + (context_score * 0.2)
        
        table_matches.append(TableMatch(
            table=table_info,
            score=total_score,
            semantic_score=base_score,
            historical_score=0.5,  # Would come from feedback history
            context_score=context_score,
            reasoning=_build_reasoning(base_score, owner_boost > 0, context_score),
            matched_entities=table_info.main_entities,
        ))
    
    # Sort by score
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


def _calculate_context_score(intent, table: Any) -> float:
    """Calculate how well table matches intent context."""
    if not intent:
        return 0.5
    
    score = 0.0
    checks = 0
    
    # Check entity match
    if intent.target_entity and table.main_entities:
        checks += 1
        if intent.target_entity.lower() in [e.lower() for e in table.main_entities]:
            score += 1.0
    
    # Check granularity match
    if intent.granularity and table.granularity:
        checks += 1
        if intent.granularity.lower() == table.granularity.lower():
            score += 1.0
    
    # Check keyword overlap
    if intent.inferred_domains and table.keywords:
        checks += 1
        table_kw = set(k.lower() for k in table.keywords)
        intent_kw = set(k.lower() for k in intent.inferred_domains)
        if table_kw & intent_kw:
            score += 1.0
    
    return score / max(checks, 1) if checks > 0 else 0.5


def _build_reasoning(semantic: float, owner_match: bool, context: float) -> str:
    """Build human-readable reasoning."""
    parts = []
    
    if semantic >= 0.7:
        parts.append(f"Alta similaridade semântica ({int(semantic * 100)}%)")
    elif semantic >= 0.5:
        parts.append(f"Similaridade moderada ({int(semantic * 100)}%)")
    
    if owner_match:
        parts.append("Dono está entre os responsáveis identificados")
    
    if context >= 0.7:
        parts.append("Contexto compatível (entidade/granularidade)")
    
    return "; ".join(parts) if parts else "Match baseado em análise geral"
