"""
Agent State Definitions

Core models for the Table Search Agent workflow.
"""

from typing import TypedDict, Optional, Literal
from pydantic import BaseModel, Field
from enum import Enum


# ============== Enums ==============

class DataExistence(str, Enum):
    EXISTS = "EXISTS"
    UNCERTAIN = "UNCERTAIN"
    NEEDS_CREATION = "NEEDS_CREATION"


class OutputMode(str, Enum):
    SINGLE = "SINGLE"    # 1 best match
    RANKING = "RANKING"  # Top 5


# ============== Core Models ==============

class DomainInfo(BaseModel):
    """Domain/business area."""
    id: str
    name: str
    description: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    
    class Config:
        frozen = True


class OwnerInfo(BaseModel):
    """Data owner."""
    id: int
    name: str
    email: Optional[str] = None
    domain_id: str
    domain_name: str
    
    class Config:
        frozen = True


class TableInfo(BaseModel):
    """Table metadata."""
    id: int
    name: str
    display_name: str
    summary: str
    domain_id: str
    domain_name: str
    owner_id: int
    owner_name: str
    keywords: list[str] = Field(default_factory=list)
    granularity: Optional[str] = None
    
    # Certification
    data_layer: Optional[Literal["SoR", "SoT", "Spec"]] = None
    is_golden_source: bool = False
    is_visao_cliente: bool = False
    update_frequency: Optional[str] = None
    inferred_product: Optional[str] = None
    
    class Config:
        frozen = True


class TableCandidate(BaseModel):
    """Table candidate from RAG search."""
    id: int
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    domain: Optional[str] = None
    schema_name: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    owner_id: Optional[int] = None
    owner_name: Optional[str] = None


class HistoricalDecision(BaseModel):
    """Historical decision for a concept-table pair."""
    concept_hash: str
    table_id: int
    approved_count: int = 0
    rejected_count: int = 0
    last_used_at: Optional[str] = None
    
    @property
    def approval_rate(self) -> float:
        """Calculate approval rate."""
        total = self.approved_count + self.rejected_count
        return self.approved_count / total if total > 0 else 0.5


class TableScore(BaseModel):
    """Score breakdown for a table candidate."""
    table_id: int
    total_score: float
    semantic_score: float = 0.0
    historical_score: float = 0.0
    keyword_score: float = 0.0
    domain_score: float = 0.0
    freshness_score: float = 0.0
    owner_trust_score: float = 0.0


# ============== Search Results ==============

class DomainMatch(BaseModel):
    """Domain match with score."""
    domain: DomainInfo
    score: float
    reasoning: str


class OwnerMatch(BaseModel):
    """Owner match with score."""
    owner: OwnerInfo
    score: float
    reasoning: str


class TableMatch(BaseModel):
    """Table match with scoring breakdown."""
    table: TableInfo
    score: float
    semantic_score: float = 0.0
    historical_score: float = 0.0
    context_score: float = 0.0
    certification_score: float = 0.0
    freshness_score: float = 0.0
    quality_score: float = 0.0
    reasoning: str
    matched_entities: list[str] = Field(default_factory=list)
    is_double_certified: bool = False
    has_product_match: bool = False


# ============== Intent ==============

class CanonicalIntent(BaseModel):
    """Normalized intent from user query."""
    data_need: str
    target_entity: Optional[str] = None
    target_segment: Optional[str] = None
    target_product: Optional[str] = None
    granularity: Optional[str] = None
    inferred_domains: list[str] = Field(default_factory=list)
    original_query: str = ""
    extraction_confidence: float = 0.0


# ============== Output Models ==============

class SingleMatchOutput(BaseModel):
    """Output for single best match."""
    domain: DomainInfo
    owner: OwnerInfo
    table: Optional[TableInfo] = None
    domain_confidence: float
    owner_confidence: float
    table_confidence: Optional[float] = None
    data_existence: DataExistence
    action: Literal["USE_TABLE", "CONFIRM_WITH_OWNER", "CREATE_INVOLVEMENT"]
    reasoning: str


class RankingOutput(BaseModel):
    """Output for ranked list."""
    domains: list[DomainMatch]
    owners: list[OwnerMatch]
    tables: list[TableMatch]
    summary: str
    clarifying_question: Optional[str] = None


# ============== Main State ==============

class AgentState(TypedDict):
    """
    LangGraph state for Table Search Agent.
    
    Flow: START → intent → domains → owners → tables → 
          → rerank → ambiguity → decide → feedback → END
    """
    # Request
    request_id: str
    output_mode: OutputMode
    
    # Input
    raw_query: str
    variable_name: Optional[str]
    variable_type: Optional[str]
    context: dict
    
    # Normalized intent
    canonical_intent: Optional[CanonicalIntent]
    
    # Search results
    matched_domains: list[DomainMatch]
    matched_owners: list[OwnerMatch]
    matched_tables: list[TableMatch]
    column_search_results: list[TableMatch]
    
    # Decision
    best_domain: Optional[DomainInfo]
    best_owner: Optional[OwnerInfo]
    best_table: Optional[TableInfo]
    data_existence: DataExistence
    overall_confidence: float
    
    # Ambiguity
    ambiguity_result: Optional[dict]
    llm_reranked: bool
    
    # Output
    single_output: Optional[SingleMatchOutput]
    ranking_output: Optional[RankingOutput]
    
    # Control
    current_step: str
    error_message: Optional[str]


def create_initial_state(
    request_id: str,
    raw_query: str,
    output_mode: OutputMode = OutputMode.SINGLE,
    variable_name: Optional[str] = None,
    variable_type: Optional[str] = None,
    context: Optional[dict] = None,
) -> AgentState:
    """Create initial state for agent."""
    return AgentState(
        request_id=request_id,
        output_mode=output_mode,
        raw_query=raw_query,
        variable_name=variable_name,
        variable_type=variable_type,
        context=context or {},
        canonical_intent=None,
        matched_domains=[],
        matched_owners=[],
        matched_tables=[],
        column_search_results=[],
        best_domain=None,
        best_owner=None,
        best_table=None,
        data_existence=DataExistence.UNCERTAIN,
        overall_confidence=0.0,
        ambiguity_result=None,
        llm_reranked=False,
        single_output=None,
        ranking_output=None,
        current_step="start",
        error_message=None,
    )

