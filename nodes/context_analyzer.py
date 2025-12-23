"""
Context Analyzer Node

First node in the workflow. Extracts and enriches variable context for search:
- Normalizes variable name
- Extracts keywords
- Identifies domain hints
- Generates embedding query
- Creates concept hash for caching
"""

import hashlib
import re
from typing import Any

from ..state import AgentState


# Portuguese stopwords for text normalization
STOPWORDS = {
    'de', 'da', 'do', 'das', 'dos', 'e', 'para', 'com', 'em', 'a', 'o', 'os', 'as',
    'um', 'uma', 'uns', 'umas', 'que', 'na', 'no', 'nas', 'nos', 'se', 'por', 'mais',
    'como', 'mas', 'foi', 'ao', 'aos', 'pela', 'pelo', 'seu', 'sua', 'seus', 'suas',
}


def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    if not text:
        return ""
    # Lowercase and remove special characters
    text = text.lower()
    text = re.sub(r'[_\-\.]', ' ', text)
    text = re.sub(r'[^a-záàâãéèêíìóòôõúùûç\s]', '', text)
    return ' '.join(text.split())


def extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from text."""
    if not text:
        return []
    
    words = normalize_text(text).split()
    keywords = [w for w in words if w not in STOPWORDS and len(w) > 2]
    
    return list(set(keywords))


def identify_domain_hints(
    variable_name: str,
    concept: str | None,
    product: str | None,
    case_context: str | None
) -> list[str]:
    """Identify domain hints from context."""
    hints = []
    
    # Combine all text sources
    all_text = ' '.join(filter(None, [variable_name, concept, product, case_context]))
    
    # Domain keyword mapping
    domain_keywords = {
        'vendas': ['venda', 'vendas', 'comercial', 'receita', 'faturamento', 'pedido'],
        'clientes': ['cliente', 'clientes', 'consumidor', 'cpf', 'cnpj', 'pessoa'],
        'produtos': ['produto', 'produtos', 'item', 'sku', 'catalogo'],
        'financeiro': ['financeiro', 'pagamento', 'cobrança', 'crédito', 'débito', 'saldo'],
        'operações': ['operação', 'operações', 'transação', 'movimento'],
        'marketing': ['campanha', 'marketing', 'promoção', 'oferta', 'comunicação'],
        'risco': ['risco', 'fraude', 'score', 'inadimplência', 'default'],
        'cadastro': ['cadastro', 'registro', 'dados mestres', 'master data'],
    }
    
    all_text_lower = all_text.lower()
    for domain, keywords in domain_keywords.items():
        if any(kw in all_text_lower for kw in keywords):
            hints.append(domain)
    
    return hints


def generate_concept_hash(variable_name: str, variable_type: str) -> str:
    """Generate deterministic hash for concept-based caching."""
    normalized = f"{normalize_text(variable_name)}:{variable_type.lower()}"
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def build_embedding_query(
    normalized_name: str,
    keywords: list[str],
    domain_hints: list[str],
    concept: str | None = None
) -> str:
    """Build optimized query for embedding search."""
    parts = []
    
    # Variable name is primary
    parts.append(normalized_name)
    
    # Add concept if available
    if concept:
        parts.append(concept)
    
    # Add domain context
    if domain_hints:
        parts.append(f"domínio: {', '.join(domain_hints)}")
    
    # Add key keywords (top 5)
    if keywords:
        parts.append(f"palavras-chave: {', '.join(keywords[:5])}")
    
    return ' | '.join(parts)


def analyze_context(state: AgentState) -> dict[str, Any]:
    """
    Node: Analyze and enrich the input context.
    
    This node:
    1. Normalizes the variable name
    2. Extracts keywords from all text fields
    3. Identifies domain hints
    4. Generates concept hash for caching
    5. Builds embedding query
    
    Returns:
        State updates for extracted context fields.
    """
    # Normalize variable name
    normalized_name = normalize_text(state["variable_name"])
    
    # Extract keywords from all sources
    all_keywords = []
    all_keywords.extend(extract_keywords(state["variable_name"]))
    if state.get("concept"):
        all_keywords.extend(extract_keywords(state["concept"]))
    if state.get("product"):
        all_keywords.extend(extract_keywords(state["product"]))
    if state.get("case_context"):
        all_keywords.extend(extract_keywords(state["case_context"]))
    
    # Deduplicate
    extracted_keywords = list(set(all_keywords))
    
    # Identify domain hints
    domain_hints = identify_domain_hints(
        state["variable_name"],
        state.get("concept"),
        state.get("product"),
        state.get("case_context")
    )
    
    # Add explicit domain if provided
    if state.get("domain"):
        domain_hints = [state["domain"]] + [d for d in domain_hints if d != state["domain"]]
    
    # Generate concept hash for caching
    concept_hash = generate_concept_hash(
        state["variable_name"],
        state.get("variable_type", "unknown")
    )
    
    # Build embedding query
    embedding_query = build_embedding_query(
        normalized_name,
        extracted_keywords,
        domain_hints,
        state.get("concept")
    )
    
    return {
        "normalized_name": normalized_name,
        "extracted_keywords": extracted_keywords,
        "domain_hints": domain_hints,
        "concept_hash": concept_hash,
        "embedding_query": embedding_query,
        "current_step": "analyzed",
    }
