"""Consequence tree data models and generation engine."""

import json
import logging
import uuid
from dataclasses import dataclass, field

from sophia.core.input_gate import _extract_json
from sophia.core.proposer import CandidateAction
from sophia.hats.prompt_assembler import assemble_prompt
from sophia.hats.schema import HatConfig
from sophia.llm.prompts.core.consequence import CONSEQUENCE_SYSTEM_PROMPT
from sophia.llm.provider import LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class ConsequenceNode:
    id: str
    description: str
    stakeholders_affected: list[str]
    probability: float  # 0.0 - 1.0
    tangibility: float  # 0.0 (abstract) - 1.0 (felt impact)
    harm_benefit: float  # -1.0 (catastrophic) to 1.0 (major benefit)
    affected_party: str
    children: list["ConsequenceNode"] = field(default_factory=list)
    is_terminal: bool = False


@dataclass
class ConsequenceTree:
    candidate_action: CandidateAction
    root_nodes: list[ConsequenceNode]
    max_depth: int
    total_nodes: int
    worst_terminal: ConsequenceNode | None
    best_terminal: ConsequenceNode | None


class ConsequenceEngine:
    """Generates consequence trees for candidate actions using LLM."""

    def __init__(
        self,
        llm: LLMProvider,
        hat_config: HatConfig | None = None,
        max_depth: int = 3,
    ):
        self.llm = llm
        self.hat_config = hat_config
        self.max_depth = max_depth

    async def analyze(self, candidate: CandidateAction) -> ConsequenceTree:
        """Generate a consequence tree for a single candidate action."""
        stakeholders_text = self._format_stakeholders()
        constraints_text = self._format_constraints()

        core_prompt = CONSEQUENCE_SYSTEM_PROMPT.format(
            max_depth=self.max_depth,
            stakeholders=stakeholders_text,
            constraints=constraints_text,
            tool_name=candidate.tool_name,
            parameters=json.dumps(candidate.parameters),
            reasoning=candidate.reasoning,
            expected_outcome=candidate.expected_outcome,
        )

        system_prompt = assemble_prompt("consequence", core_prompt, self.hat_config)

        response = await self.llm.complete(
            system_prompt=system_prompt,
            user_message=(
                f"Analyze the consequences of calling {candidate.tool_name} "
                f"with parameters {json.dumps(candidate.parameters)}."
            ),
            response_format={"type": "json"},
        )

        parsed = json.loads(_extract_json(response.content))
        root_nodes = self._parse_nodes(parsed.get("consequences", []))

        self._validate_stakeholder_refs(root_nodes)

        total = self._count_nodes(root_nodes)
        terminals = self._collect_terminals(root_nodes)
        worst = min(terminals, key=lambda n: n.harm_benefit, default=None)
        best = max(terminals, key=lambda n: n.harm_benefit, default=None)

        tree = ConsequenceTree(
            candidate_action=candidate,
            root_nodes=root_nodes,
            max_depth=self.max_depth,
            total_nodes=total,
            worst_terminal=worst,
            best_terminal=best,
        )

        logger.info(
            "Consequence tree for '%s': %d nodes, worst=%.2f, best=%.2f",
            candidate.tool_name,
            total,
            worst.harm_benefit if worst else 0.0,
            best.harm_benefit if best else 0.0,
        )

        return tree

    def _parse_nodes(self, data: list[dict]) -> list[ConsequenceNode]:
        """Recursively parse JSON into ConsequenceNode objects."""
        nodes = []
        for item in data:
            children_data = item.get("children", [])
            children = self._parse_nodes(children_data) if children_data else []

            is_terminal = item.get("is_terminal", len(children) == 0)

            node = ConsequenceNode(
                id=uuid.uuid4().hex[:12],
                description=item.get("description", ""),
                stakeholders_affected=item.get("stakeholders_affected", []),
                probability=self._clamp(item.get("probability", 0.5), 0.0, 1.0),
                tangibility=self._clamp(item.get("tangibility", 0.5), 0.0, 1.0),
                harm_benefit=self._clamp(item.get("harm_benefit", 0.0), -1.0, 1.0),
                affected_party=item.get("affected_party", ""),
                children=children,
                is_terminal=is_terminal,
            )
            nodes.append(node)

        return nodes

    def _validate_stakeholder_refs(self, nodes: list[ConsequenceNode]) -> None:
        """Log warnings for invalid stakeholder references."""
        if not self.hat_config:
            return

        valid_ids = {s.id for s in self.hat_config.stakeholders.stakeholders}
        self._validate_refs_recursive(nodes, valid_ids)

    def _validate_refs_recursive(
        self, nodes: list[ConsequenceNode], valid_ids: set[str]
    ) -> None:
        for node in nodes:
            for ref in node.stakeholders_affected:
                if ref not in valid_ids:
                    logger.warning(
                        "Invalid stakeholder ref '%s' in node '%s' (valid: %s)",
                        ref,
                        node.description[:60],
                        valid_ids,
                    )
            if node.affected_party and node.affected_party not in valid_ids:
                logger.warning(
                    "Invalid affected_party '%s' in node '%s'",
                    node.affected_party,
                    node.description[:60],
                )
            if node.children:
                self._validate_refs_recursive(node.children, valid_ids)

    def _format_stakeholders(self) -> str:
        if not self.hat_config:
            return "No stakeholders defined."
        stakeholders = self.hat_config.stakeholders.stakeholders
        if not stakeholders:
            return "No stakeholders defined."
        lines = []
        for s in stakeholders:
            lines.append(
                f"- {s.id} ({s.name}): interests={s.interests}, "
                f"harm_sensitivity={s.harm_sensitivity}, weight={s.weight}"
            )
        return "\n".join(lines)

    def _format_constraints(self) -> str:
        if not self.hat_config or not self.hat_config.constraints:
            return "No domain constraints."
        return json.dumps(self.hat_config.constraints, indent=2)

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    @staticmethod
    def _count_nodes(nodes: list[ConsequenceNode]) -> int:
        count = 0
        for node in nodes:
            count += 1
            count += ConsequenceEngine._count_nodes(node.children)
        return count

    @staticmethod
    def _collect_terminals(nodes: list[ConsequenceNode]) -> list[ConsequenceNode]:
        terminals = []
        for node in nodes:
            if node.is_terminal:
                terminals.append(node)
            terminals.extend(ConsequenceEngine._collect_terminals(node.children))
        return terminals
