"""
Disambiguation Scorer

Multi-dimensional scoring for table disambiguation.
Combines: Certification, Freshness, Quality, Context.
"""

from typing import Optional, Literal
from datetime import datetime
from dataclasses import dataclass

from ..quality import get_quality_cache


# Certification scores (Tier 1 & 2)
CERTIFICATION_SCORES = {
    "golden_source": 1.0,
    "visao_cliente": 1.0,
    "SoT": 0.75,
    "Spec": 0.50,
    "SoR": 0.30,
}

# Weights by use case
USE_CASE_WEIGHTS = {
    "operational": {"cert": 0.25, "fresh": 0.40, "quality": 0.35},
    "analytical": {"cert": 0.30, "fresh": 0.15, "quality": 0.55},
    "regulatory": {"cert": 0.40, "fresh": 0.10, "quality": 0.50},
    "default": {"cert": 0.30, "fresh": 0.30, "quality": 0.40},
}


@dataclass
class TableMetadataForScoring:
    """Table metadata needed for disambiguation scoring."""
    table_name: str
    data_layer: Optional[Literal["SoR", "SoT", "Spec"]] = None
    is_golden_source: bool = False
    is_visao_cliente: bool = False
    domain: Optional[str] = None
    update_frequency: Optional[str] = None  # "realtime", "daily", "weekly", "monthly"
    last_updated: Optional[datetime] = None
    inferred_product: Optional[str] = None


@dataclass
class DisambiguationScore:
    """Complete disambiguation score with breakdown."""
    table_name: str
    total_score: float
    
    # Component scores
    certification_score: float
    freshness_score: float
    quality_score: float
    context_score: float
    
    # Metadata
    weights_used: dict
    use_case: str
    reasoning: str
    
    # Flags
    is_double_certified: bool = False
    has_product_match: bool = False


def calculate_certification_score(table: TableMetadataForScoring) -> tuple[float, str]:
    """
    Calculate certification score.
    
    Hierarchy:
    1. Golden Source + Visão Cliente (double certified)
    2. Golden Source OR Visão Cliente
    3. SoT
    4. Spec
    5. SoR
    """
    reasons = []
    score = CERTIFICATION_SCORES.get(table.data_layer, 0.3)
    
    if table.is_golden_source and table.is_visao_cliente:
        score = 1.0
        reasons.append("✓✓ Duplamente certificada")
    elif table.is_golden_source:
        score = max(score, 1.0)
        reasons.append("✓ Golden Source")
    elif table.is_visao_cliente:
        score = max(score, 1.0)
        reasons.append("✓ Visão Cliente")
    elif table.data_layer:
        reasons.append(f"Camada: {table.data_layer}")
    
    return score, " | ".join(reasons) if reasons else "Não certificada"


def calculate_freshness_score(table: TableMetadataForScoring) -> tuple[float, str]:
    """
    Calculate freshness score based on update frequency and recency.
    """
    if not table.last_updated:
        return 0.5, "Sem info de atualização"
    
    hours_since = (datetime.utcnow() - table.last_updated).total_seconds() / 3600
    freq = table.update_frequency or "unknown"
    
    # Expected freshness by frequency
    thresholds = {
        "realtime": (1, 4),      # Fresh < 1h, Stale > 4h
        "daily": (26, 50),       # Fresh < 26h, Stale > 50h
        "weekly": (170, 200),    # Fresh < 7d+2h, Stale > 8d
        "monthly": (750, 800),   # Fresh < 31d, Stale > 33d
    }
    
    fresh_limit, stale_limit = thresholds.get(freq, (72, 168))
    
    if hours_since <= fresh_limit:
        score = 1.0
        reason = f"✓ Atualizada há {int(hours_since)}h ({freq})"
    elif hours_since <= stale_limit:
        score = 0.7
        reason = f"○ Atualizada há {int(hours_since)}h ({freq})"
    else:
        score = 0.4
        reason = f"⚠️ Desatualizada há {int(hours_since)}h ({freq})"
    
    return score, reason


def calculate_quality_score(table_name: str) -> tuple[float, str]:
    """
    Get quality score from cache (synced from Athena).
    """
    cache = get_quality_cache()
    cached = cache.get(table_name)
    
    if not cached:
        return 0.5, "Sem métrica de qualidade"
    
    score = cached.quality_score / 100.0
    
    if score >= 0.9:
        reason = f"✓ Qualidade: {cached.quality_score:.1f}/100"
    elif score >= 0.7:
        reason = f"○ Qualidade: {cached.quality_score:.1f}/100"
    else:
        reason = f"⚠️ Qualidade: {cached.quality_score:.1f}/100"
    
    return score, reason


def calculate_context_score(
    table: TableMetadataForScoring,
    user_domain: Optional[str] = None,
    user_product: Optional[str] = None,
) -> tuple[float, str]:
    """
    Calculate context match score.
    """
    score = 0.0
    reasons = []
    
    # Domain match
    if user_domain and table.domain:
        if user_domain.lower() == table.domain.lower():
            score += 0.5
            reasons.append(f"✓ Domínio: {table.domain}")
    
    # Product match (especially for Spec layer)
    if user_product and table.inferred_product:
        if user_product.lower() in table.inferred_product.lower():
            score += 0.5
            reasons.append(f"✓ Produto: {table.inferred_product}")
    elif user_product and table.data_layer == "Spec":
        # Check product in table name
        if user_product.lower() in table.table_name.lower():
            score += 0.5
            reasons.append(f"✓ Produto match no nome")
    
    if not reasons:
        return 0.3, "Contexto não verificado"
    
    return min(score, 1.0), " | ".join(reasons)


def calculate_disambiguation_score(
    table: TableMetadataForScoring,
    use_case: str = "default",
    user_domain: Optional[str] = None,
    user_product: Optional[str] = None,
) -> DisambiguationScore:
    """
    Calculate complete disambiguation score for a table.
    
    Args:
        table: Table metadata
        use_case: "operational", "analytical", "regulatory", or "default"
        user_domain: User's requested domain
        user_product: User's requested product
    
    Returns:
        DisambiguationScore with all components
    """
    weights = USE_CASE_WEIGHTS.get(use_case, USE_CASE_WEIGHTS["default"])
    
    # Calculate components
    cert_score, cert_reason = calculate_certification_score(table)
    fresh_score, fresh_reason = calculate_freshness_score(table)
    quality_score, quality_reason = calculate_quality_score(table.table_name)
    context_score, context_reason = calculate_context_score(table, user_domain, user_product)
    
    # Weighted total
    total = (
        cert_score * weights["cert"] +
        fresh_score * weights["fresh"] +
        quality_score * weights["quality"]
    )
    
    # Context boost (additive, not weighted)
    if context_score > 0.5:
        total = min(1.0, total + 0.1)
    
    # Build reasoning
    reasoning_parts = [cert_reason, fresh_reason, quality_reason]
    if context_reason != "Contexto não verificado":
        reasoning_parts.append(context_reason)
    
    return DisambiguationScore(
        table_name=table.table_name,
        total_score=total,
        certification_score=cert_score,
        freshness_score=fresh_score,
        quality_score=quality_score,
        context_score=context_score,
        weights_used=weights,
        use_case=use_case,
        reasoning=" | ".join(reasoning_parts),
        is_double_certified=table.is_golden_source and table.is_visao_cliente,
        has_product_match=context_score > 0.5 and user_product is not None,
    )
