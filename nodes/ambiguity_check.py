"""
Ambiguity Check Node

Checks for ambiguity in search results and generates clarifying questions.
"""

from typing import Any

from ..state import AgentState
from ..disambiguation.ambiguity_detector import get_ambiguity_detector, AmbiguityResult


async def check_ambiguity(state: AgentState) -> dict[str, Any]:
    """
    Node: Check for ambiguity in search results.
    
    Runs after table/column search to detect if results are ambiguous.
    If ambiguous, generates clarifying question for user.
    """
    table_matches = state.get("matched_tables", [])
    domain_matches = state.get("matched_domains", [])
    context = state.get("context", {})
    intent = state.get("canonical_intent")
    
    user_product = context.get("produto") or (intent.target_product if intent else None)
    
    detector = get_ambiguity_detector()
    
    result = detector.detect(
        table_matches=table_matches,
        domain_matches=domain_matches,
        user_product=user_product,
    )
    
    return {
        "ambiguity_result": result,
        "current_step": "ambiguity_checked",
    }


def should_ask_clarification(result: AmbiguityResult) -> bool:
    """
    Determine if we should ask user for clarification.
    
    Only ask if:
    1. Ambiguity was detected
    2. We have options to present
    3. Confidence is not too low (otherwise just say "not found")
    """
    if not result.is_ambiguous:
        return False
    
    if not result.options:
        return False
    
    # If confidence is very low, don't ask - just say not found
    if result.confidence < 0.2:
        return False
    
    return True


def format_clarification_message(result: AmbiguityResult) -> str:
    """
    Format the clarification message for the user.
    
    Returns a human-readable message with options.
    """
    lines = [result.clarifying_question or "Preciso de mais informações:"]
    lines.append("")
    
    for i, option in enumerate(result.options, 1):
        lines.append(f"{i}. **{option.label}**")
        if option.description:
            lines.append(f"   {option.description}")
    
    if result.provisional_table_id:
        lines.append("")
        lines.append(f"_Sugestão provisória: opção 1_")
    
    return "\n".join(lines)
