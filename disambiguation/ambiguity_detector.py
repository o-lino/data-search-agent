"""
Ambiguity Detector

Detects ambiguous search results and generates clarifying questions.
Handles: score ties, domain conflicts, homonymy, and fragmentation.
"""

from typing import Optional, Literal
from dataclasses import dataclass, field
from enum import Enum

from ..state import TableMatch, DomainMatch


class AmbiguityType(str, Enum):
    """Types of ambiguity detected."""
    NONE = "NONE"                    # Clear winner
    SCORE_TIE = "SCORE_TIE"          # Top results too close
    DOMAIN_CONFLICT = "DOMAIN_CONFLICT"  # Different domains
    HOMONYMY = "HOMONYMY"            # Same name, different contexts
    FRAGMENTATION = "FRAGMENTATION"   # Same data across tables
    LOW_CONFIDENCE = "LOW_CONFIDENCE"  # All scores too low
    MULTIPLE_PRODUCTS = "MULTIPLE_PRODUCTS"  # Multiple product matches


@dataclass
class ClarifyingOption:
    """An option presented to the user for clarification."""
    id: str
    label: str
    description: str
    table_id: Optional[int] = None
    domain: Optional[str] = None


@dataclass
class AmbiguityResult:
    """Result of ambiguity detection."""
    type: AmbiguityType
    is_ambiguous: bool
    confidence: float  # How confident we are in the ambiguity detection
    
    # Question to ask user
    clarifying_question: Optional[str] = None
    options: list[ClarifyingOption] = field(default_factory=list)
    
    # Still provide provisional recommendation
    provisional_table_id: Optional[int] = None
    provisional_reasoning: str = ""
    
    # Debug info
    detection_details: dict = field(default_factory=dict)


class AmbiguityDetector:
    """
    Detects ambiguity in search results.
    
    Detection Rules:
    1. SCORE_TIE: |score1 - score2| < threshold
    2. DOMAIN_CONFLICT: top2 in different domains
    3. HOMONYMY: same column/table name, different semantic contexts
    4. FRAGMENTATION: multiple tables cover same data (different time/geo)
    5. LOW_CONFIDENCE: top score < minimum threshold
    6. MULTIPLE_PRODUCTS: query matches multiple product-specific tables
    """
    
    def __init__(
        self,
        score_tie_threshold: float = 0.05,
        minimum_confidence: float = 0.40,
        high_confidence: float = 0.75,
    ):
        self.score_tie_threshold = score_tie_threshold
        self.minimum_confidence = minimum_confidence
        self.high_confidence = high_confidence
    
    def detect(
        self,
        table_matches: list[TableMatch],
        domain_matches: list[DomainMatch] = None,
        user_product: Optional[str] = None,
    ) -> AmbiguityResult:
        """
        Detect ambiguity in search results.
        
        Returns AmbiguityResult with type and clarifying question if needed.
        """
        if not table_matches:
            return AmbiguityResult(
                type=AmbiguityType.NONE,
                is_ambiguous=False,
                confidence=0.0,
                clarifying_question="Não encontrei tabelas para essa busca. Pode reformular?",
            )
        
        top1 = table_matches[0]
        
        # Rule 5: LOW_CONFIDENCE
        if top1.score < self.minimum_confidence:
            return self._create_low_confidence_result(table_matches)
        
        # Only one result - no ambiguity
        if len(table_matches) == 1:
            return AmbiguityResult(
                type=AmbiguityType.NONE,
                is_ambiguous=False,
                confidence=top1.score,
                provisional_table_id=top1.table.id,
                provisional_reasoning=top1.reasoning,
            )
        
        top2 = table_matches[1]
        
        # Rule 1: SCORE_TIE
        if abs(top1.score - top2.score) < self.score_tie_threshold:
            # Check if it's domain conflict
            if top1.table.domain_name != top2.table.domain_name:
                return self._create_domain_conflict_result(top1, top2)
            
            # Check for product conflict
            if self._has_product_conflict(top1, top2, user_product):
                return self._create_product_conflict_result(table_matches[:5], user_product)
            
            # Generic score tie
            return self._create_score_tie_result(top1, top2)
        
        # Rule 6: MULTIPLE_PRODUCTS (even if scores differ)
        if user_product and self._has_multiple_product_matches(table_matches[:5]):
            return self._create_product_conflict_result(table_matches[:5], user_product)
        
        # Rule 3: HOMONYMY detection
        homonymy = self._detect_homonymy(table_matches[:5])
        if homonymy:
            return homonymy
        
        # Rule 4: FRAGMENTATION detection
        fragmentation = self._detect_fragmentation(table_matches[:5])
        if fragmentation:
            return fragmentation
        
        # Clear winner
        return AmbiguityResult(
            type=AmbiguityType.NONE,
            is_ambiguous=False,
            confidence=top1.score,
            provisional_table_id=top1.table.id,
            provisional_reasoning=top1.reasoning,
        )
    
    def _create_low_confidence_result(
        self, 
        matches: list[TableMatch]
    ) -> AmbiguityResult:
        """Create result for low confidence scenario."""
        options = [
            ClarifyingOption(
                id=f"table_{m.table.id}",
                label=m.table.display_name,
                description=f"{m.table.domain_name} | Score: {m.score:.0%}",
                table_id=m.table.id,
                domain=m.table.domain_name,
            )
            for m in matches[:5]
        ]
        
        return AmbiguityResult(
            type=AmbiguityType.LOW_CONFIDENCE,
            is_ambiguous=True,
            confidence=matches[0].score if matches else 0,
            clarifying_question="Não tenho certeza sobre a melhor opção. Qual destas tabelas você precisa?",
            options=options,
            provisional_table_id=matches[0].table.id if matches else None,
            detection_details={"top_score": matches[0].score if matches else 0},
        )
    
    def _create_score_tie_result(
        self, 
        top1: TableMatch, 
        top2: TableMatch
    ) -> AmbiguityResult:
        """Create result for score tie."""
        return AmbiguityResult(
            type=AmbiguityType.SCORE_TIE,
            is_ambiguous=True,
            confidence=top1.score,
            clarifying_question=f"Encontrei 2 tabelas com relevância similar. Qual você prefere?",
            options=[
                ClarifyingOption(
                    id=f"table_{top1.table.id}",
                    label=top1.table.display_name,
                    description=top1.reasoning,
                    table_id=top1.table.id,
                ),
                ClarifyingOption(
                    id=f"table_{top2.table.id}",
                    label=top2.table.display_name,
                    description=top2.reasoning,
                    table_id=top2.table.id,
                ),
            ],
            provisional_table_id=top1.table.id,
            provisional_reasoning="Empate de score, escolhida a primeira",
            detection_details={
                "score_diff": abs(top1.score - top2.score),
                "top1_score": top1.score,
                "top2_score": top2.score,
            },
        )
    
    def _create_domain_conflict_result(
        self, 
        top1: TableMatch, 
        top2: TableMatch
    ) -> AmbiguityResult:
        """Create result for domain conflict."""
        return AmbiguityResult(
            type=AmbiguityType.DOMAIN_CONFLICT,
            is_ambiguous=True,
            confidence=top1.score,
            clarifying_question=f"Você precisa de dados de {top1.table.domain_name} ou {top2.table.domain_name}?",
            options=[
                ClarifyingOption(
                    id=f"domain_{top1.table.domain_name}",
                    label=top1.table.domain_name,
                    description=f"Tabela: {top1.table.display_name}",
                    table_id=top1.table.id,
                    domain=top1.table.domain_name,
                ),
                ClarifyingOption(
                    id=f"domain_{top2.table.domain_name}",
                    label=top2.table.domain_name,
                    description=f"Tabela: {top2.table.display_name}",
                    table_id=top2.table.id,
                    domain=top2.table.domain_name,
                ),
            ],
            provisional_table_id=top1.table.id,
            provisional_reasoning=f"Conflito de domínio entre {top1.table.domain_name} e {top2.table.domain_name}",
            detection_details={
                "domains": [top1.table.domain_name, top2.table.domain_name],
            },
        )
    
    def _create_product_conflict_result(
        self,
        matches: list[TableMatch],
        user_product: Optional[str],
    ) -> AmbiguityResult:
        """Create result for multiple product matches."""
        products = set()
        options = []
        
        for m in matches:
            product = m.table.inferred_product or self._extract_product_from_name(m.table.name)
            if product and product not in products:
                products.add(product)
                options.append(ClarifyingOption(
                    id=f"product_{product}",
                    label=product.title(),
                    description=f"Tabela: {m.table.display_name}",
                    table_id=m.table.id,
                ))
        
        return AmbiguityResult(
            type=AmbiguityType.MULTIPLE_PRODUCTS,
            is_ambiguous=True,
            confidence=matches[0].score,
            clarifying_question=f"Encontrei dados para múltiplos produtos. Qual você precisa?",
            options=options[:5],
            provisional_table_id=matches[0].table.id,
            detection_details={"products": list(products)},
        )
    
    def _has_product_conflict(
        self,
        top1: TableMatch,
        top2: TableMatch,
        user_product: Optional[str],
    ) -> bool:
        """Check if there's a product conflict between top results."""
        product1 = top1.table.inferred_product or self._extract_product_from_name(top1.table.name)
        product2 = top2.table.inferred_product or self._extract_product_from_name(top2.table.name)
        
        return product1 and product2 and product1 != product2
    
    def _has_multiple_product_matches(self, matches: list[TableMatch]) -> bool:
        """Check if multiple products are present in matches."""
        products = set()
        for m in matches:
            product = m.table.inferred_product or self._extract_product_from_name(m.table.name)
            if product:
                products.add(product)
        return len(products) > 1
    
    def _extract_product_from_name(self, table_name: str) -> Optional[str]:
        """Extract product name from table name."""
        products = ["consig", "imob", "auto", "cartao", "cdc", "varejo", "corporate"]
        name_lower = table_name.lower()
        for p in products:
            if p in name_lower:
                return p
        return None
    
    def _detect_homonymy(self, matches: list[TableMatch]) -> Optional[AmbiguityResult]:
        """Detect if same column/table name appears in different contexts."""
        # Check for same name in different domains
        names_seen = {}
        for m in matches:
            name = m.table.name
            if name in names_seen:
                other = names_seen[name]
                if m.table.domain_name != other.table.domain_name:
                    return AmbiguityResult(
                        type=AmbiguityType.HOMONYMY,
                        is_ambiguous=True,
                        confidence=m.score,
                        clarifying_question=f"'{name}' existe em contextos diferentes. Qual você precisa?",
                        options=[
                            ClarifyingOption(
                                id=f"context_{other.table.domain_name}",
                                label=f"{name} ({other.table.domain_name})",
                                description=other.table.summary[:100],
                                table_id=other.table.id,
                            ),
                            ClarifyingOption(
                                id=f"context_{m.table.domain_name}",
                                label=f"{name} ({m.table.domain_name})",
                                description=m.table.summary[:100],
                                table_id=m.table.id,
                            ),
                        ],
                        provisional_table_id=other.table.id,
                        detection_details={"homonym": name},
                    )
            names_seen[name] = m
        
        return None
    
    def _detect_fragmentation(self, matches: list[TableMatch]) -> Optional[AmbiguityResult]:
        """Detect if same data is fragmented across multiple tables."""
        # Check for similar names suggesting fragmentation
        base_names = {}
        for m in matches:
            # Extract base name (remove suffixes like _v1, _2024, _hist)
            base = self._get_base_name(m.table.name)
            if base in base_names:
                other = base_names[base]
                return AmbiguityResult(
                    type=AmbiguityType.FRAGMENTATION,
                    is_ambiguous=True,
                    confidence=m.score,
                    clarifying_question=f"Esses dados estão em tabelas separadas. Qual período/versão você precisa?",
                    options=[
                        ClarifyingOption(
                            id=f"version_{other.table.name}",
                            label=other.table.display_name,
                            description=other.table.summary[:100],
                            table_id=other.table.id,
                        ),
                        ClarifyingOption(
                            id=f"version_{m.table.name}",
                            label=m.table.display_name,
                            description=m.table.summary[:100],
                            table_id=m.table.id,
                        ),
                    ],
                    provisional_table_id=other.table.id,
                    detection_details={"base_name": base},
                )
            base_names[base] = m
        
        return None
    
    def _get_base_name(self, table_name: str) -> str:
        """Get base name removing version/date suffixes."""
        import re
        # Remove common suffixes
        patterns = [
            r'_v\d+$',      # _v1, _v2
            r'_\d{4}$',     # _2024
            r'_hist$',      # _hist
            r'_old$',       # _old
            r'_new$',       # _new
            r'_bkp$',       # _bkp
        ]
        result = table_name.lower()
        for pattern in patterns:
            result = re.sub(pattern, '', result)
        return result


# Global instance
_detector: Optional[AmbiguityDetector] = None


def get_ambiguity_detector() -> AmbiguityDetector:
    """Get or create ambiguity detector."""
    global _detector
    if _detector is None:
        _detector = AmbiguityDetector()
    return _detector
