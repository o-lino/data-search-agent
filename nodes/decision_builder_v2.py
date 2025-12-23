"""
Decision Builder Node V2

Builds final output based on output mode (SINGLE/RANKING).
Always includes Domain + Owner. Table is optional.
"""

from typing import Any, Literal

from ..state import (
    AgentState,
    OutputMode,
    SingleMatchOutput,
    RankingOutput,
    DataExistence,
)


def decide_v2(state: AgentState) -> dict[str, Any]:
    """
    Node: Build final output based on search results.
    
    Always provides Domain + Owner.
    Table is provided if confidence is high enough.
    """
    # Get best matches
    best_domain = state["matched_domains"][0].domain if state["matched_domains"] else None
    best_owner = state["matched_owners"][0].owner if state["matched_owners"] else None
    best_table = state["matched_tables"][0].table if state["matched_tables"] else None
    
    # Calculate confidences
    domain_conf = state["matched_domains"][0].score if state["matched_domains"] else 0.0
    owner_conf = state["matched_owners"][0].score if state["matched_owners"] else 0.0
    table_conf = state["matched_tables"][0].score if state["matched_tables"] else None
    
    # Overall confidence
    overall = (domain_conf * 0.3 + owner_conf * 0.3 + (table_conf or 0) * 0.4)
    
    # Determine action
    data_existence = state.get("data_existence", DataExistence.UNCERTAIN)
    
    if data_existence == DataExistence.EXISTS and table_conf and table_conf >= 0.70:
        action: Literal["USE_TABLE", "CONFIRM_WITH_OWNER", "CREATE_INVOLVEMENT"] = "USE_TABLE"
    elif data_existence == DataExistence.NEEDS_CREATION:
        action = "CREATE_INVOLVEMENT"
    else:
        action = "CONFIRM_WITH_OWNER"
    
    # Build reasoning
    reasoning = _build_final_reasoning(
        best_domain, best_owner, best_table, data_existence, action
    )
    
    # Build output based on mode
    single_output = None
    ranking_output = None
    
    if state["output_mode"] == OutputMode.SINGLE:
        if best_domain and best_owner:
            single_output = SingleMatchOutput(
                domain=best_domain,
                owner=best_owner,
                table=best_table if table_conf and table_conf >= 0.40 else None,
                domain_confidence=domain_conf,
                owner_confidence=owner_conf,
                table_confidence=table_conf,
                data_existence=data_existence,
                action=action,
                reasoning=reasoning,
            )
    
    elif state["output_mode"] == OutputMode.RANKING:
        # Build summary
        if best_table:
            summary = f"Melhor opção: {best_table.display_name} ({best_owner.name if best_owner else 'N/A'})"
        elif best_owner:
            summary = f"Responsável sugerido: {best_owner.name} ({best_domain.name if best_domain else 'N/A'})"
        else:
            summary = "Nenhum resultado encontrado com confiança adequada."
        
        # Clarifying question if uncertain
        clarifying = None
        if overall < 0.50:
            clarifying = _generate_clarifying_question(state)
        
        ranking_output = RankingOutput(
            domains=state.get("matched_domains", [])[:5],
            owners=state.get("matched_owners", [])[:5],
            tables=state.get("matched_tables", [])[:5],
            summary=summary,
            clarifying_question=clarifying,
        )
    
    return {
        "best_domain": best_domain,
        "best_owner": best_owner,
        "best_table": best_table,
        "overall_confidence": overall,
        "single_output": single_output,
        "ranking_output": ranking_output,
        "current_step": "decided",
    }


def _build_final_reasoning(domain, owner, table, existence, action) -> str:
    """Build final reasoning text."""
    parts = []
    
    if domain:
        parts.append(f"Domínio: {domain.name}")
    if owner:
        parts.append(f"Responsável: {owner.name}")
    if table:
        parts.append(f"Tabela sugerida: {table.display_name}")
    
    if existence == DataExistence.NEEDS_CREATION:
        parts.append("Dados não encontrados - solicitar criação")
    elif existence == DataExistence.UNCERTAIN:
        parts.append("Validação com responsável recomendada")
    
    if action == "USE_TABLE":
        parts.append("✅ Alta confiança - usar tabela sugerida")
    elif action == "CONFIRM_WITH_OWNER":
        parts.append("⚠️ Confirmar com responsável antes de usar")
    elif action == "CREATE_INVOLVEMENT":
        parts.append("📝 Abrir solicitação de criação de dados")
    
    return " | ".join(parts)


def _generate_clarifying_question(state: AgentState) -> str:
    """Generate a clarifying question when confidence is low."""
    intent = state.get("canonical_intent")
    
    if not intent:
        return "Você pode descrever melhor qual tipo de dado está buscando?"
    
    if not intent.target_entity:
        return "Qual entidade principal você precisa? (cliente, produto, transação, etc.)"
    
    if not intent.target_segment:
        return "Para qual segmento? (varejo, corporate, PF, PJ, etc.)"
    
    if not intent.granularity:
        return "Qual a granularidade desejada? (diária, mensal, por transação, etc.)"
    
    return "Pode detalhar mais o contexto de uso desses dados?"
