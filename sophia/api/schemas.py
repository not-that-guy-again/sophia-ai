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


class ChatResponse(BaseModel):
    response: str
    intent: IntentResponse
    proposal: ProposalResponse
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
