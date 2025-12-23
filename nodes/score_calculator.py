"""
Score Calculator Node

Calculates deterministic scores for each candidate table using weighted factors:
- Semantic similarity (from retrieval)
- Historical approval rate
- Keyword overlap
- Domain matching
- Freshness (recency of usage)
- Owner trust score
"""

from typing import Any

from ..state import AgentState, TableScore, TableCandidate, HistoricalDecision
from src.core.config import settings


def calculate_semantic_score(table: TableCandidate, keywords: list[str]) -> float:
    """Calculate semantic similarity based on keyword overlap."""
    if not keywords:
        return 0.5  # Neutral if no keywords
    
    # Combine table text fields
    table_text = ' '.join(filter(None, [
        table.name.lower(),
        table.display_name.lower(),
        (table.description or "").lower(),
        ' '.join(table.keywords).lower() if table.keywords else "",
    ]))
    
    # Count keyword matches
    matches = sum(1 for kw in keywords if kw.lower() in table_text)
    
    return min(1.0, matches / len(keywords))


def calculate_historical_score(
    table_id: int,
    historical: list[HistoricalDecision],
    min_decisions: int
) -> float:
    """Calculate score from historical decisions."""
    for h in historical:
        if h.table_id == table_id:
            total = h.approved_count + h.rejected_count
            if total >= min_decisions:
                return h.approval_rate
    
    return 0.5  # Neutral if no history


def calculate_keyword_score(table: TableCandidate, keywords: list[str]) -> float:
    """Calculate keyword overlap score."""
    if not keywords or not table.keywords:
        return 0.0
    
    table_kw_lower = {kw.lower() for kw in table.keywords}
    input_kw_lower = {kw.lower() for kw in keywords}
    
    intersection = table_kw_lower & input_kw_lower
    union = table_kw_lower | input_kw_lower
    
    return len(intersection) / len(union) if union else 0.0


def calculate_domain_score(table: TableCandidate, domain_hints: list[str]) -> float:
    """Calculate domain matching score."""
    if not domain_hints or not table.domain:
        return 0.5  # Neutral
    
    table_domain = table.domain.lower()
    
    for i, hint in enumerate(domain_hints):
        if hint.lower() == table_domain:
            # Higher score for earlier hints (more specific)
            return 1.0 - (i * 0.1)
    
    return 0.0


def calculate_freshness_score(historical: list[HistoricalDecision], table_id: int) -> float:
    """Calculate freshness based on recent usage."""
    for h in historical:
        if h.table_id == table_id and h.last_used_at:
            # Recent usage = higher score
            # This is simplified - in production, parse dates
            return 0.8
    
    return 0.5  # Neutral if no recent usage


def calculate_owner_trust_score(table: TableCandidate) -> float:
    """Calculate owner trust score (placeholder for future implementation)."""
    # In production, this would look at:
    # - Owner response rate
    # - Average approval rate
    # - Response time
    return 0.7 if table.owner_id else 0.5


def calculate_total_score(
    table: TableCandidate,
    keywords: list[str],
    domain_hints: list[str],
    historical: list[HistoricalDecision],
    weights: dict[str, float]
) -> TableScore:
    """Calculate total weighted score for a table."""
    
    semantic = calculate_semantic_score(table, keywords)
    historical_score = calculate_historical_score(
        table.id, historical, settings.min_decisions_for_pattern
    )
    keyword = calculate_keyword_score(table, keywords)
    domain = calculate_domain_score(table, domain_hints)
    freshness = calculate_freshness_score(historical, table.id)
    owner_trust = calculate_owner_trust_score(table)
    
    total = (
        semantic * weights["semantic"] +
        historical_score * weights["historical"] +
        keyword * weights["keyword"] +
        domain * weights["domain"] +
        freshness * weights["freshness"] +
        owner_trust * weights["owner_trust"]
    )
    
    return TableScore(
        table_id=table.id,
        total_score=total,
        semantic_score=semantic,
        historical_score=historical_score,
        keyword_score=keyword,
        domain_score=domain,
        freshness_score=freshness,
        owner_trust_score=owner_trust,
    )


def calculate_scores(state: AgentState) -> dict[str, Any]:
    """
    Node: Calculate deterministic scores for all candidate tables.
    
    Uses weighted scoring with configurable weights from settings.
    
    Returns:
        State update with scores dictionary.
    """
    weights = settings.scoring_weights
    
    scores = {}
    for table in state["candidate_tables"]:
        score = calculate_total_score(
            table=table,
            keywords=state["extracted_keywords"],
            domain_hints=state["domain_hints"],
            historical=state["historical_decisions"],
            weights=weights,
        )
        scores[table.id] = score
    
    return {
        "scores": scores,
        "current_step": "scored",
    }
