import json
import logging
from dataclasses import dataclass, field

from sophia.core.input_gate import Intent, _extract_json
from sophia.hats.prompt_assembler import assemble_prompt
from sophia.hats.schema import HatConfig
from sophia.llm.provider import LLMProvider
from sophia.llm.prompts.core.proposer import PROPOSER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


@dataclass
class CandidateAction:
    tool_name: str
    parameters: dict = field(default_factory=dict)
    reasoning: str = ""
    expected_outcome: str = ""


@dataclass
class Proposal:
    intent: Intent
    candidates: list[CandidateAction] = field(default_factory=list)


class Proposer:
    """Generates candidate actions for a parsed intent using LLM."""

    def __init__(
        self,
        llm: LLMProvider,
        tool_definitions: str,
        domain_constraints: dict,
        hat_config: HatConfig | None = None,
    ):
        self.llm = llm
        self.tool_definitions = tool_definitions
        self.domain_constraints = domain_constraints
        self.hat_config = hat_config

    async def propose(self, intent: Intent) -> Proposal:
        core_prompt = PROPOSER_SYSTEM_PROMPT.format(
            tool_definitions=self.tool_definitions,
            domain_constraints=json.dumps(self.domain_constraints, indent=2),
            action_requested=intent.action_requested,
            target=intent.target or "none",
            parameters=json.dumps(intent.parameters),
        )
        system_prompt = assemble_prompt("proposer", core_prompt, self.hat_config)

        response = await self.llm.complete(
            system_prompt=system_prompt,
            user_message=intent.raw_message,
            response_format={"type": "json"},
        )

        logger.debug("Proposer raw LLM response: %s", response.content)

        parsed = json.loads(_extract_json(response.content))
        candidates = []
        for c in parsed.get("candidates", []):
            candidates.append(
                CandidateAction(
                    tool_name=c.get("tool_name", ""),
                    parameters=c.get("parameters", {}),
                    reasoning=c.get("reasoning", ""),
                    expected_outcome=c.get("expected_outcome", ""),
                )
            )

        return Proposal(intent=intent, candidates=candidates)
