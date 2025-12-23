"""
LLM Reranker

Uses LLM to intelligently rerank search results based on context and reasoning.
Only activates when top results are close in score (ambiguous ranking).
"""

from typing import Any, Optional
import json

from ..state import AgentState, TableMatch


# Reranking prompt template
RERANK_PROMPT = """Você é um especialista em dados corporativos. Analise estas tabelas candidatas para a busca do usuário e reordene-as baseado em relevância.

## Query do Usuário
{query}

## Contexto Adicional
{context}

## Tabelas Candidatas (ordenadas por score numérico)
{tables_summary}

## Critérios de Avaliação
1. **Match de conceito**: A tabela atende ao que o usuário busca?
2. **Granularidade**: A granularidade (diária, mensal) é adequada?
3. **Qualidade**: Considere certificações (Golden Source, Visão Cliente)
4. **Recência**: Dados atualizados são preferíveis
5. **Especificidade**: Tabela específica > genérica se match de contexto

## Resposta
Retorne um JSON com:
1. "ranking": lista de IDs na nova ordem (melhor primeiro)
2. "reasoning": explicação da reordenação
3. "confidence": 0.0-1.0 na reordenação

Exemplo:
{{"ranking": [3, 1, 2], "reasoning": "Tabela 3 tem match exato de produto...", "confidence": 0.85}}

JSON:"""


def build_tables_summary(matches: list[TableMatch]) -> str:
    """Build summary of tables for LLM prompt."""
    lines = []
    for i, m in enumerate(matches, 1):
        cert_info = []
        if m.table.is_golden_source:
            cert_info.append("Golden Source")
        if m.table.is_visao_cliente:
            cert_info.append("Visão Cliente")
        if m.table.data_layer:
            cert_info.append(m.table.data_layer)
        
        cert_str = f" [{', '.join(cert_info)}]" if cert_info else ""
        
        lines.append(f"""
**{i}. {m.table.display_name}** (ID: {m.table.id}){cert_str}
- Score: {m.score:.2f}
- Domínio: {m.table.domain_name}
- Owner: {m.table.owner_name}
- Resumo: {m.table.summary[:150]}
- Reasoning atual: {m.reasoning}
""")
    
    return "\n".join(lines)


def build_context_summary(state: AgentState) -> str:
    """Build context summary for LLM prompt."""
    intent = state.get("canonical_intent")
    context = state.get("context", {})
    
    parts = []
    
    if intent:
        if intent.target_product:
            parts.append(f"Produto: {intent.target_product}")
        if intent.target_segment:
            parts.append(f"Segmento: {intent.target_segment}")
        if intent.target_entity:
            parts.append(f"Entidade: {intent.target_entity}")
        if intent.granularity:
            parts.append(f"Granularidade: {intent.granularity}")
    
    use_case = context.get("use_case", "default")
    parts.append(f"Use case: {use_case}")
    
    return " | ".join(parts) if parts else "Sem contexto adicional"


async def should_rerank(matches: list[TableMatch], threshold: float = 0.15) -> bool:
    """
    Determine if reranking is needed.
    
    Only rerank if top scores are close (ambiguous ordering).
    """
    if len(matches) < 2:
        return False
    
    # Check score spread in top 5
    top5 = matches[:5]
    if len(top5) < 2:
        return False
    
    score_spread = top5[0].score - top5[-1].score
    
    # If spread is small, ordering is ambiguous - rerank
    return score_spread < threshold


async def rerank_with_llm(
    state: AgentState,
    matches: list[TableMatch],
    max_to_rerank: int = 10,
) -> list[TableMatch]:
    """
    Rerank matches using LLM.
    
    Args:
        state: Current agent state
        matches: Matches to rerank
        max_to_rerank: Maximum number to send to LLM
    
    Returns:
        Reranked list of matches
    """
    if len(matches) <= 1:
        return matches
    
    # Take top N for reranking
    to_rerank = matches[:max_to_rerank]
    remainder = matches[max_to_rerank:]
    
    # Build prompt
    query = state.get("raw_query", "")
    if state.get("canonical_intent"):
        query = state["canonical_intent"].data_need or query
    
    context = build_context_summary(state)
    tables_summary = build_tables_summary(to_rerank)
    
    prompt = RERANK_PROMPT.format(
        query=query,
        context=context,
        tables_summary=tables_summary,
    )
    
    try:
        # Call LLM
        from openai import AsyncOpenAI
        import os
        
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Parse JSON response
        # Handle markdown code blocks
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]
        
        result = json.loads(result_text)
        
        new_ranking = result.get("ranking", [])
        reasoning = result.get("reasoning", "")
        confidence = result.get("confidence", 0.5)
        
        # Reorder matches based on LLM ranking
        id_to_match = {m.table.id: m for m in to_rerank}
        reranked = []
        
        for table_id in new_ranking:
            if table_id in id_to_match:
                match = id_to_match[table_id]
                # Add LLM reasoning to match
                match.reasoning = f"{match.reasoning} | 🤖 LLM: {reasoning[:100]}"
                reranked.append(match)
                del id_to_match[table_id]
        
        # Add any matches not in LLM ranking (shouldn't happen but safety)
        reranked.extend(id_to_match.values())
        
        # Add remainder
        reranked.extend(remainder)
        
        return reranked
        
    except Exception as e:
        print(f"Warning: LLM reranking failed: {e}")
        # Return original order if LLM fails
        return matches


async def llm_rerank_node(state: AgentState) -> dict[str, Any]:
    """
    Node: LLM-based reranking of search results.
    
    Only activates when:
    1. Multiple results exist
    2. Top scores are close (ambiguous ordering)
    3. Reranking is not disabled in context
    """
    matches = state.get("matched_tables", [])
    context = state.get("context", {})
    
    # Check if reranking is disabled
    if context.get("skip_rerank", False):
        return {"current_step": "rerank_skipped"}
    
    # Check if reranking is needed
    if not await should_rerank(matches):
        return {
            "llm_reranked": False,
            "current_step": "rerank_not_needed",
        }
    
    # Perform reranking
    reranked = await rerank_with_llm(state, matches)
    
    return {
        "matched_tables": reranked,
        "llm_reranked": True,
        "current_step": "rerank_complete",
    }


# Utility function for manual reranking
async def rerank_results(
    query: str,
    matches: list[TableMatch],
    context: dict = None,
) -> list[TableMatch]:
    """
    Utility function to rerank results without full state.
    
    Useful for testing or manual reranking.
    """
    # Build minimal state
    from ..state import create_initial_state, OutputMode
    
    state = create_initial_state(
        request_id="manual",
        raw_query=query,
        output_mode=OutputMode.RANKING,
        context=context or {},
    )
    state["matched_tables"] = matches
    
    return await rerank_with_llm(state, matches)
