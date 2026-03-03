// --- Backend model mirrors (match sophia/api/schemas.py exactly) ---

export interface Intent {
  action_requested: string;
  target: string | null;
  parameters: Record<string, unknown>;
  requestor_context: Record<string, unknown>;
  raw_message: string;
  hat_name: string;
}

export interface CandidateAction {
  tool_name: string;
  parameters: Record<string, unknown>;
  reasoning: string;
  expected_outcome: string;
}

export interface ToolResult {
  success: boolean;
  data: unknown;
  message: string;
}

export interface ConsequenceNode {
  id: string;
  description: string;
  stakeholders_affected: string[];
  probability: number;
  tangibility: number;
  harm_benefit: number; // -1.0 to 1.0
  affected_party: string;
  children: ConsequenceNode[];
  is_terminal: boolean;
}

export interface ConsequenceTree {
  candidate_tool_name: string;
  root_nodes: ConsequenceNode[];
  max_depth: number;
  total_nodes: number;
  worst_harm: number | null;
  best_benefit: number | null;
}

export interface EvaluatorResult {
  evaluator_name: string;
  score: number; // -1.0 to 1.0
  confidence: number; // 0.0 to 1.0
  flags: string[];
  reasoning: string;
  key_concerns: string[];
}

export interface RiskClassification {
  tier: RiskTier;
  weighted_score: number;
  individual_scores: Record<string, number>;
  flags: string[];
  override_reason: string | null;
  explanation: string;
}

export interface ExecutionResult {
  action_taken: CandidateAction;
  tool_result: ToolResult;
  risk_tier: string;
}

export interface HatSummary {
  name: string;
  display_name: string;
  description: string;
  version: string;
  tools: string[];
}

export interface HatActive extends HatSummary {
  constraints: Record<string, unknown>;
  stakeholder_count: number;
}

// --- UI-specific types ---

export type RiskTier = "GREEN" | "YELLOW" | "ORANGE" | "RED";

export interface PipelineTrace {
  intent: Intent | null;
  proposals: CandidateAction[];
  trees: ConsequenceTree[];
  evaluations: EvaluatorResult[];
  risk: RiskClassification | null;
  execution: ExecutionResult | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  trace: PipelineTrace | null;
  tier: RiskTier | null;
  timestamp: number;
  confirmationStatus?: "pending" | "approved" | "declined";
}

// --- WebSocket event types ---

export type WsEvent =
  | { event: "hat_equipped"; data: { name: string; display_name: string } }
  | { event: "intent_parsed"; data: Intent }
  | { event: "proposals_generated"; data: { candidates: CandidateAction[] } }
  | { event: "consequences_analyzed"; data: { trees: ConsequenceTree[] } }
  | { event: "evaluator_complete"; data: EvaluatorResult }
  | { event: "risk_classified"; data: RiskClassification }
  | {
      event: "action_executed";
      data: ExecutionResult;
    }
  | { event: "response_ready"; data: { response: string } }
  | { event: "error"; data: { message: string } };

// --- Audit log ---

export interface AuditEntry {
  id: string;
  timestamp: number;
  userMessage: string;
  response: string;
  tier: RiskTier | null;
  trace: PipelineTrace;
}
