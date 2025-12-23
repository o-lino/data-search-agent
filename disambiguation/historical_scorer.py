"""
Historical Score Calculator

Calculates learning-based scores from feedback history.
Integrates with the disambiguation scorer.
"""

from typing import Optional
from ..memory.feedback_store import get_feedback_store, generate_concept_hash
from ..state import CanonicalIntent


async def get_historical_score_for_table(
    intent: CanonicalIntent,
    table_id: int,
    min_samples: int = 3,
) -> tuple[float, bool]:
    """
    Get historical approval rate for a table given an intent.
    
    Args:
        intent: Normalized canonical intent
        table_id: Table to check
        min_samples: Minimum samples for reliable score
    
    Returns:
        (score, is_reliable) - Score 0-1 and whether we have enough data
    """
    if not intent:
        return 0.5, False
    
    # Generate concept hash from intent
    intent_data = {
        "data_need": intent.data_need,
        "target_entity": intent.target_entity,
        "target_product": intent.target_product,
        "target_segment": intent.target_segment,
        "granularity": intent.granularity,
    }
    concept_hash = generate_concept_hash(intent_data)
    
    # Query feedback store
    store = get_feedback_store()
    score, count = await store.get_historical_score(
        concept_hash=concept_hash,
        table_id=table_id,
        min_samples=min_samples,
    )
    
    is_reliable = count >= min_samples or count == -1  # -1 = cached
    
    return score, is_reliable


async def get_historically_approved_tables(
    intent: CanonicalIntent,
    limit: int = 5,
) -> list[dict]:
    """
    Get tables historically approved for similar intents.
    
    Useful for boosting candidates that worked before.
    """
    if not intent:
        return []
    
    intent_data = {
        "data_need": intent.data_need,
        "target_entity": intent.target_entity,
        "target_product": intent.target_product,
        "target_segment": intent.target_segment,
        "granularity": intent.granularity,
    }
    concept_hash = generate_concept_hash(intent_data)
    
    store = get_feedback_store()
    top_tables = await store.get_top_tables_for_concept(concept_hash, limit)
    
    return [
        {
            "table_id": table_id,
            "approval_rate": rate,
            "sample_count": count,
        }
        for table_id, rate, count in top_tables
    ]


async def record_decision_feedback(
    intent: CanonicalIntent,
    table_id: int,
    outcome: str,  # APPROVED, REJECTED, MODIFIED
    actual_table_id: Optional[int] = None,
    confidence: float = 0.0,
    use_case: str = "default",
    request_id: str = "",
    domain_id: Optional[str] = None,
    owner_id: Optional[int] = None,
) -> int:
    """
    Record feedback for a decision.
    
    This is called when user approves, rejects, or modifies a recommendation.
    """
    from ..memory.feedback_store import DecisionRecord
    
    intent_data = {
        "data_need": intent.data_need if intent else "",
        "target_entity": intent.target_entity if intent else None,
        "target_product": intent.target_product if intent else None,
        "target_segment": intent.target_segment if intent else None,
        "granularity": intent.granularity if intent else None,
    }
    concept_hash = generate_concept_hash(intent_data)
    
    record = DecisionRecord(
        request_id=request_id,
        concept_hash=concept_hash,
        domain_id=domain_id,
        owner_id=owner_id,
        table_id=table_id,
        outcome=outcome,
        actual_table_id=actual_table_id,
        confidence_at_decision=confidence,
        use_case=use_case,
    )
    
    store = get_feedback_store()
    return await store.record_decision(record)
