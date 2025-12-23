"""
Enhanced Feedback Store

Captures and analyzes justifications for learning and improvement.
"""

from typing import Optional, Literal
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import re


# ============== Justification Categories ==============

class RejectionReason(str, Enum):
    """Why a recommendation was rejected."""
    WRONG_GRANULARITY = "wrong_granularity"      # Diária vs mensal
    WRONG_PRODUCT = "wrong_product"              # Consignado vs imobiliário
    WRONG_SEGMENT = "wrong_segment"              # Varejo vs corporate
    WRONG_ENTITY = "wrong_entity"                # Cliente vs transação
    OUTDATED_DATA = "outdated_data"              # Dados antigos
    INCOMPLETE_DATA = "incomplete_data"          # Dados faltando
    WRONG_SCOPE = "wrong_scope"                  # Muito amplo/específico
    PERMISSION_DENIED = "permission_denied"      # Sem acesso
    TABLE_DEPRECATED = "table_deprecated"        # Tabela descontinuada
    BETTER_ALTERNATIVE = "better_alternative"    # Existe opção melhor
    CONCEPT_MISMATCH = "concept_mismatch"        # Não era isso que precisava
    QUALITY_ISSUES = "quality_issues"            # Problemas de qualidade
    OTHER = "other"


class ApprovalReason(str, Enum):
    """Why a recommendation was approved."""
    EXACT_MATCH = "exact_match"                  # Exatamente o que precisava
    GOOD_ENOUGH = "good_enough"                  # Serve para o propósito
    ONLY_OPTION = "only_option"                  # Única disponível
    RECOMMENDED_BY_OWNER = "recommended_by_owner"
    CERTIFIED_SOURCE = "certified_source"        # Fonte certificada
    ALREADY_USING = "already_using"              # Já usava essa


# ============== Enhanced Record ==============

@dataclass
class DecisionRecord:
    """A decision record with justification."""
    id: Optional[int] = None
    request_id: str = ""
    concept_hash: str = ""
    
    # What was recommended
    domain_id: Optional[str] = None
    owner_id: Optional[int] = None
    table_id: Optional[int] = None
    
    # Outcome
    outcome: Literal["APPROVED", "REJECTED", "MODIFIED"] = "APPROVED"
    actual_table_id: Optional[int] = None
    
    # Context at decision
    confidence_at_decision: float = 0.0
    use_case: str = "default"
    
    # --- NEW: Justification ---
    justification_text: str = ""              # Free text from user
    justification_category: Optional[str] = None  # Inferred category
    justification_keywords: list[str] = field(default_factory=list)
    
    # Learning signals
    was_close_match: bool = False             # Almost correct?
    suggested_improvement: Optional[str] = None
    
    created_at: Optional[datetime] = None


# ============== Justification Analyzer ==============

class JustificationAnalyzer:
    """
    Analyzes justification text to extract learning signals.
    """
    
    # Keywords mapping to categories
    REJECTION_KEYWORDS = {
        RejectionReason.WRONG_GRANULARITY: [
            "granularidade", "diária", "mensal", "anual", "agregação",
            "muito agregado", "muito detalhado", "nível errado"
        ],
        RejectionReason.WRONG_PRODUCT: [
            "produto errado", "não é consignado", "não é imobiliário",
            "produto diferente", "outro produto"
        ],
        RejectionReason.WRONG_SEGMENT: [
            "segmento errado", "varejo", "corporate", "pj", "pf",
            "pessoa física", "pessoa jurídica"
        ],
        RejectionReason.WRONG_ENTITY: [
            "entidade errada", "não é cliente", "não é transação",
            "queria conta", "queria produto"
        ],
        RejectionReason.OUTDATED_DATA: [
            "desatualizado", "antigo", "dados velhos", "não tem 2024",
            "só tem até", "defasado"
        ],
        RejectionReason.INCOMPLETE_DATA: [
            "incompleto", "faltando", "não tem o campo", "sem a coluna",
            "dados parciais"
        ],
        RejectionReason.WRONG_SCOPE: [
            "muito amplo", "muito específico", "escopo errado",
            "só uma parte", "precisava de tudo"
        ],
        RejectionReason.PERMISSION_DENIED: [
            "sem acesso", "não tenho permissão", "bloqueado", "restrito"
        ],
        RejectionReason.TABLE_DEPRECATED: [
            "descontinuada", "deprecated", "não usar mais", "substituída",
            "legado", "desativada"
        ],
        RejectionReason.BETTER_ALTERNATIVE: [
            "existe melhor", "tem outra", "prefiro a", "já uso outra",
            "alternativa melhor"
        ],
        RejectionReason.CONCEPT_MISMATCH: [
            "não era isso", "entendeu errado", "não é o que eu queria",
            "conceito errado", "mal interpretado"
        ],
        RejectionReason.QUALITY_ISSUES: [
            "qualidade ruim", "dados errados", "inconsistente",
            "não confiável", "muitos nulos"
        ],
    }
    
    APPROVAL_KEYWORDS = {
        ApprovalReason.EXACT_MATCH: [
            "perfeito", "exatamente", "era isso", "correto", "certinho"
        ],
        ApprovalReason.GOOD_ENOUGH: [
            "serve", "ok", "dá pro gasto", "funciona", "pode ser"
        ],
        ApprovalReason.ONLY_OPTION: [
            "única opção", "só tem essa", "não tem outra"
        ],
        ApprovalReason.CERTIFIED_SOURCE: [
            "certificada", "fonte oficial", "golden source", "sot"
        ],
        ApprovalReason.ALREADY_USING: [
            "já uso", "já usamos", "é a que usamos", "padrão nosso"
        ],
    }
    
    def analyze(
        self, 
        text: str, 
        outcome: str,
    ) -> tuple[Optional[str], list[str], bool]:
        """
        Analyze justification text.
        
        Returns:
            (category, keywords_found, was_close_match)
        """
        if not text:
            return None, [], False
        
        text_lower = text.lower()
        keywords_found = []
        category = None
        was_close = False
        
        # Check for "close match" indicators
        close_indicators = ["quase", "quase certo", "parecido", "similar", "perto"]
        was_close = any(ind in text_lower for ind in close_indicators)
        
        if outcome == "REJECTED":
            # Check rejection categories
            for reason, keywords in self.REJECTION_KEYWORDS.items():
                for kw in keywords:
                    if kw in text_lower:
                        keywords_found.append(kw)
                        if category is None:
                            category = reason.value
            
            if category is None:
                category = RejectionReason.OTHER.value
                
        elif outcome == "APPROVED":
            # Check approval categories
            for reason, keywords in self.APPROVAL_KEYWORDS.items():
                for kw in keywords:
                    if kw in text_lower:
                        keywords_found.append(kw)
                        if category is None:
                            category = reason.value
            
            if category is None:
                category = ApprovalReason.GOOD_ENOUGH.value
        
        return category, keywords_found, was_close
    
    def extract_improvement_suggestion(self, text: str) -> Optional[str]:
        """Extract improvement suggestions from text."""
        patterns = [
            r"deveria (?:ser|usar|recomendar) (.+?)(?:\.|,|$)",
            r"melhor seria (.+?)(?:\.|,|$)",
            r"preciso de (.+?)(?:\.|,|$)",
            r"queria (.+?)(?:\.|,|$)",
            r"correto é (.+?)(?:\.|,|$)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                return match.group(1).strip()
        
        return None


# ============== Enhanced Feedback Store ==============

class FeedbackStore:
    """
    Store and analyze decision feedback.
    """
    
    def __init__(self, use_postgres: bool = False, connection_string: str = None):
        self.use_postgres = use_postgres
        self.connection_string = connection_string
        self.analyzer = JustificationAnalyzer()
        
        # Storage
        self._memory_store: dict[str, list[DecisionRecord]] = {}
        
        # Score cache
        self._score_cache: dict[str, float] = {}
        self._cache_ttl_minutes = 5
        self._cache_updated: dict[str, datetime] = {}
        
        # Learning aggregates
        self._category_stats: dict[str, dict[str, int]] = {}  # table_id -> {category: count}
        self._keyword_stats: dict[str, dict[str, int]] = {}   # keyword -> {table_id: count}
    
    async def record_decision(
        self, 
        record: DecisionRecord,
        justification: str = "",
    ) -> int:
        """Record a decision with justification analysis."""
        record.created_at = datetime.utcnow()
        record.justification_text = justification
        
        # Analyze justification
        if justification:
            category, keywords, was_close = self.analyzer.analyze(
                justification, 
                record.outcome
            )
            record.justification_category = category
            record.justification_keywords = keywords
            record.was_close_match = was_close
            record.suggested_improvement = self.analyzer.extract_improvement_suggestion(
                justification
            )
            
            # Update learning stats
            self._update_learning_stats(record)
        
        if self.use_postgres:
            return await self._insert_postgres(record)
        
        return self._insert_memory(record)
    
    def _update_learning_stats(self, record: DecisionRecord) -> None:
        """Update learning statistics from record."""
        table_key = str(record.table_id)
        
        # Category stats
        if record.justification_category:
            if table_key not in self._category_stats:
                self._category_stats[table_key] = {}
            cat = record.justification_category
            self._category_stats[table_key][cat] = \
                self._category_stats[table_key].get(cat, 0) + 1
        
        # Keyword stats
        for kw in record.justification_keywords:
            if kw not in self._keyword_stats:
                self._keyword_stats[kw] = {}
            self._keyword_stats[kw][table_key] = \
                self._keyword_stats[kw].get(table_key, 0) + 1
    
    def _insert_memory(self, record: DecisionRecord) -> int:
        """Insert into in-memory store."""
        key = f"{record.concept_hash}:{record.table_id}"
        
        if key not in self._memory_store:
            self._memory_store[key] = []
        
        record.id = len(self._memory_store[key]) + 1
        self._memory_store[key].append(record)
        
        self._invalidate_cache(key)
        return record.id
    
    async def _insert_postgres(self, record: DecisionRecord) -> int:
        """Insert into PostgreSQL."""
        raise NotImplementedError("PostgreSQL not configured")
    
    async def get_historical_score(
        self, 
        concept_hash: str, 
        table_id: int,
        min_samples: int = 3,
    ) -> tuple[float, int]:
        """Get historical approval rate with justification weighting."""
        cache_key = f"{concept_hash}:{table_id}"
        
        if self._is_cache_valid(cache_key):
            return self._score_cache.get(cache_key, 0.5), -1
        
        return self._query_memory_weighted(concept_hash, table_id, min_samples)
    
    def _query_memory_weighted(
        self, 
        concept_hash: str, 
        table_id: int,
        min_samples: int,
    ) -> tuple[float, int]:
        """Query with justification-weighted scoring."""
        key = f"{concept_hash}:{table_id}"
        records = self._memory_store.get(key, [])
        
        if len(records) < min_samples:
            return 0.5, len(records)
        
        # Weighted scoring based on justification
        total_weight = 0
        weighted_score = 0
        
        for r in records:
            # Base weight
            weight = 1.0
            
            # Boost weight for strong justifications
            if r.justification_category:
                if r.outcome == "APPROVED":
                    if r.justification_category == ApprovalReason.EXACT_MATCH.value:
                        weight = 2.0  # Strong positive signal
                    elif r.justification_category == ApprovalReason.CERTIFIED_SOURCE.value:
                        weight = 1.5
                elif r.outcome == "REJECTED":
                    if r.justification_category in [
                        RejectionReason.CONCEPT_MISMATCH.value,
                        RejectionReason.WRONG_ENTITY.value,
                    ]:
                        weight = 2.0  # Strong negative signal
                    elif r.was_close_match:
                        weight = 0.5  # Reduce penalty for close matches
            
            score = 1.0 if r.outcome == "APPROVED" else 0.0
            weighted_score += score * weight
            total_weight += weight
        
        final_score = weighted_score / total_weight if total_weight > 0 else 0.5
        
        # Cache
        self._score_cache[key] = final_score
        self._cache_updated[key] = datetime.utcnow()
        
        return final_score, len(records)
    
    def get_rejection_patterns(self, table_id: int) -> dict[str, int]:
        """Get common rejection reasons for a table."""
        return self._category_stats.get(str(table_id), {})
    
    def get_tables_with_issue(self, category: str) -> list[tuple[int, int]]:
        """Get tables commonly rejected for a specific reason."""
        results = []
        for table_key, categories in self._category_stats.items():
            if category in categories:
                results.append((int(table_key), categories[category]))
        return sorted(results, key=lambda x: x[1], reverse=True)
    
    def get_learning_insights(self) -> dict:
        """Get aggregated learning insights."""
        total_approved = 0
        total_rejected = 0
        category_totals: dict[str, int] = {}
        close_matches = 0
        
        for records in self._memory_store.values():
            for r in records:
                if r.outcome == "APPROVED":
                    total_approved += 1
                else:
                    total_rejected += 1
                
                if r.justification_category:
                    category_totals[r.justification_category] = \
                        category_totals.get(r.justification_category, 0) + 1
                
                if r.was_close_match:
                    close_matches += 1
        
        # Top rejection reasons
        rejection_categories = {
            k: v for k, v in category_totals.items() 
            if k in [r.value for r in RejectionReason]
        }
        
        return {
            "total_decisions": total_approved + total_rejected,
            "approval_rate": total_approved / (total_approved + total_rejected) if total_approved + total_rejected > 0 else 0,
            "close_match_rate": close_matches / (total_approved + total_rejected) if total_approved + total_rejected > 0 else 0,
            "top_rejection_reasons": sorted(
                rejection_categories.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:5],
            "category_distribution": category_totals,
        }
    
    def _invalidate_cache(self, key: str) -> None:
        """Invalidate cache for a key."""
        self._score_cache.pop(key, None)
        self._cache_updated.pop(key, None)
    
    def _is_cache_valid(self, key: str) -> bool:
        """Check if cache is still valid."""
        if key not in self._cache_updated:
            return False
        age = (datetime.utcnow() - self._cache_updated[key]).total_seconds() / 60
        return age < self._cache_ttl_minutes
    
    @property
    def stats(self) -> dict:
        """Get store statistics."""
        total_records = sum(len(r) for r in self._memory_store.values())
        with_justification = sum(
            1 for records in self._memory_store.values() 
            for r in records if r.justification_text
        )
        
        return {
            "total_records": total_records,
            "with_justification": with_justification,
            "justification_rate": with_justification / total_records if total_records > 0 else 0,
            "unique_concepts": len(set(k.split(":")[0] for k in self._memory_store.keys())),
            "unique_pairs": len(self._memory_store),
            "categories_tracked": len(self._category_stats),
            "storage": "postgres" if self.use_postgres else "memory",
        }


def generate_concept_hash(intent_data: dict) -> str:
    """Generate hash from normalized intent."""
    key_parts = [
        intent_data.get("data_need", ""),
        intent_data.get("target_entity", ""),
        intent_data.get("target_product", ""),
        intent_data.get("target_segment", ""),
        intent_data.get("granularity", ""),
    ]
    normalized = "|".join(sorted(filter(None, key_parts))).lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


# Global instance
_feedback_store: Optional[FeedbackStore] = None


def get_feedback_store(use_postgres: bool = False) -> FeedbackStore:
    """Get or create feedback store."""
    global _feedback_store
    if _feedback_store is None:
        _feedback_store = FeedbackStore(use_postgres=use_postgres)
    return _feedback_store
