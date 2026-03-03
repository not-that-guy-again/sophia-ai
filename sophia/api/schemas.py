from pydantic import BaseModel
from typing import Any


class ChatRequest(BaseModel):
    message: str


class ToolResultResponse(BaseModel):
    success: bool
    data: Any
    message: str


class CandidateActionResponse(BaseModel):
    tool_name: str
    parameters: dict
    reasoning: str
    expected_outcome: str


class IntentResponse(BaseModel):
    action_requested: str
    target: str | None
    parameters: dict
    requestor_context: dict
    raw_message: str
    hat_name: str = ""


class ExecutionResponse(BaseModel):
    action_taken: CandidateActionResponse
    tool_result: ToolResultResponse
    risk_tier: str


class ProposalResponse(BaseModel):
    candidates: list[CandidateActionResponse]


class ConsequenceNodeResponse(BaseModel):
    id: str
    description: str
    stakeholders_affected: list[str]
    probability: float
    tangibility: float
    harm_benefit: float
    affected_party: str
    children: list["ConsequenceNodeResponse"] = []
    is_terminal: bool


ConsequenceNodeResponse.model_rebuild()


class ConsequenceTreeResponse(BaseModel):
    candidate_tool_name: str
    root_nodes: list[ConsequenceNodeResponse]
    max_depth: int
    total_nodes: int
    worst_harm: float | None
    best_benefit: float | None


class EvaluatorResultResponse(BaseModel):
    evaluator_name: str
    score: float
    confidence: float
    flags: list[str] = []
    reasoning: str = ""
    key_concerns: list[str] = []


class RiskClassificationResponse(BaseModel):
    tier: str
    weighted_score: float
    individual_scores: dict[str, float] = {}
    flags: list[str] = []
    override_reason: str | None = None
    explanation: str = ""


class ChatResponse(BaseModel):
    response: str
    intent: IntentResponse
    proposal: ProposalResponse
    consequence_trees: list[ConsequenceTreeResponse] = []
    evaluations: list[EvaluatorResultResponse] = []
    risk_classification: RiskClassificationResponse | None = None
    execution: ExecutionResponse
    metadata: dict = {}


class HealthResponse(BaseModel):
    status: str
    version: str


class ToolDefinitionResponse(BaseModel):
    name: str
    description: str
    parameters: dict
    authority_level: str
    max_financial_impact: float | None


class HatSummaryResponse(BaseModel):
    name: str
    display_name: str
    description: str
    version: str
    tools: list[str]


class HatActiveResponse(BaseModel):
    name: str
    display_name: str
    description: str
    version: str
    tools: list[str]
    constraints: dict
    stakeholder_count: int
