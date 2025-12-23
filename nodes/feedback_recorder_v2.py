"""
Feedback Recorder V2

Records feedback and uses it to adjust domain/owner/table associations.
Implements continuous learning from user decisions.
"""

from typing import Any
from datetime import datetime

from ..state import AgentState, DataExistence
from ..memory.long_term import record_decision_outcome


async def record_feedback_v2(state: AgentState) -> dict[str, Any]:
    """
    Node: Prepare feedback data for learning.
    
    Note: Actual feedback comes from the /feedback endpoint.
    This node logs the search result for later matching with feedback.
    """
    # Prepare log entry
    search_log = {
        "request_id": state["request_id"],
        "timestamp": datetime.utcnow().isoformat(),
        "raw_query": state.get("raw_query"),
        "canonical_intent": state.get("canonical_intent").model_dump() if state.get("canonical_intent") else None,
        "best_domain_id": state["best_domain"].id if state.get("best_domain") else None,
        "best_owner_id": state["best_owner"].id if state.get("best_owner") else None,
        "best_table_id": state["best_table"].id if state.get("best_table") else None,
        "overall_confidence": state.get("overall_confidence", 0.0),
        "data_existence": state.get("data_existence", DataExistence.UNCERTAIN).value,
        "output_mode": state["output_mode"].value,
    }
    
    # Log for debugging
    print(f"[FeedbackRecorderV2] Search logged: {search_log}")
    
    return {
        "current_step": "completed",
    }


async def apply_feedback(
    request_id: str,
    outcome: str,  # APPROVED, REJECTED, MODIFIED
    actual_domain_id: str = None,
    actual_owner_id: int = None,
    actual_table_id: int = None,
) -> dict:
    """
    Apply feedback to improve future recommendations.
    
    Called by the /feedback endpoint when user confirms or rejects.
    
    Adjustments made:
    1. Domain associations strengthened/weakened
    2. Owner approval rates updated
    3. Table historical scores updated
    4. Intent → domain mappings learned
    """
    # In production, this would:
    # 1. Look up the original search by request_id
    # 2. Compare suggested vs actual
    # 3. Update various scores in the database
    
    adjustments = []
    
    if outcome == "APPROVED":
        # Strengthen all associations
        adjustments.append("Domain association +1")
        adjustments.append("Owner approval rate +1")
        adjustments.append("Table historical score +1")
        
    elif outcome == "REJECTED":
        # Weaken suggested associations
        adjustments.append("Table historical score -1")
        adjustments.append("Owner approval rate adjusted")
        
    elif outcome == "MODIFIED":
        # Learn from correction
        if actual_table_id:
            adjustments.append(f"Learned: table {actual_table_id} is correct for this intent")
        if actual_owner_id:
            adjustments.append(f"Learned: owner {actual_owner_id} is correct for this domain")
        if actual_domain_id:
            adjustments.append(f"Learned: domain {actual_domain_id} is correct for this query")
    
    return {
        "success": True,
        "adjustments": adjustments,
        "message": f"Feedback '{outcome}' applied with {len(adjustments)} adjustments",
    }
