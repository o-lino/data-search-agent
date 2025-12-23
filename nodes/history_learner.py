"""
History Learner Node

Records the decision for future learning:
- Logs the recommendation made
- Updates decision context cache
- Prepares data for long-term memory
"""

from typing import Any
from datetime import datetime

from ..state import AgentState


async def record_history(state: AgentState) -> dict[str, Any]:
    """
    Node: Record the decision for learning.
    
    This node:
    1. Logs the search request and result
    2. Prepares data for long-term memory update
    
    Note: Actual database writes happen asynchronously after response.
    The feedback endpoint is used to record user approval/rejection.
    
    Returns:
        State update with final step marker.
    """
    # Prepare decision record (would be sent to memory service)
    decision_record = {
        "request_id": state["request_id"],
        "concept_hash": state["concept_hash"],
        "variable_name": state["variable_name"],
        "variable_type": state.get("variable_type", "unknown"),
        "timestamp": datetime.utcnow().isoformat(),
        "recommendations_count": len(state["recommendations"]),
        "top_table_id": state["top_recommendation"].table.id if state["top_recommendation"] else None,
        "top_score": state["top_recommendation"].score.total_score if state["top_recommendation"] else 0.0,
        "confidence_level": state["confidence_level"].value,
        "domain_hints": state["domain_hints"],
        "keywords": state["extracted_keywords"][:10],  # Limit for storage
    }
    
    # In production, this would be sent to the memory service
    # For now, we just log it
    print(f"[HistoryLearner] Recording decision: {decision_record}")
    
    return {
        "current_step": "completed",
        "iteration": state["iteration"] + 1,
    }
