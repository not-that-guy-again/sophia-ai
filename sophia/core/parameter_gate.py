"""Pre-flight parameter gate (ADR-019).

Deterministic validation step that runs between the proposer and the
consequence engine. Catches candidates with placeholder or missing required
parameters and short-circuits to conversational bypass instead of running
the full pipeline.
"""

import logging
from dataclasses import dataclass, field

from sophia.core.proposer import CandidateAction, Proposal
from sophia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

CONVERSE_TOOL_NAME = "converse"

CORE_PLACEHOLDERS: set[str] = {
    "unknown",
    "tbd",
    "n/a",
    "none",
    "placeholder",
    "todo",
    "?",
    "???",
}


@dataclass
class ParameterValidation:
    """Validation result for a single candidate's parameters."""

    candidate: CandidateAction
    passed: bool
    failures: list[str] = field(default_factory=list)


@dataclass
class GateResult:
    """Result of running the parameter gate on a full proposal."""

    original_candidates: list[CandidateAction]
    surviving_candidates: list[CandidateAction]
    validations: list[ParameterValidation] = field(default_factory=list)
    promoted_converse: bool = False


class ParameterGate:
    """Validates candidate parameters against tool schemas before the consequence engine.

    Catches placeholder values (e.g. "UNKNOWN", "TBD") and missing required
    parameters without any LLM calls — purely deterministic.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        extra_placeholders: set[str] | None = None,
    ):
        self.tool_registry = tool_registry
        self.placeholders = CORE_PLACEHOLDERS | {
            p.strip().lower() for p in (extra_placeholders or set())
        }

    def validate(self, proposal: Proposal) -> GateResult:
        """Validate all candidates in a proposal against their tool schemas."""
        validations: list[ParameterValidation] = []
        passing: list[CandidateAction] = []
        converse_candidates: list[CandidateAction] = []
        has_non_converse = False

        for candidate in proposal.candidates:
            if candidate.tool_name == CONVERSE_TOOL_NAME:
                validations.append(ParameterValidation(candidate=candidate, passed=True))
                converse_candidates.append(candidate)
                continue

            has_non_converse = True
            validation = self._validate_candidate(candidate)
            validations.append(validation)
            if validation.passed:
                passing.append(candidate)

        # Build surviving candidates
        if passing:
            # At least one non-converse candidate passed — keep passers + converse
            surviving = passing + converse_candidates
            promoted_converse = False
        elif has_non_converse:
            # ALL non-converse candidates failed
            if converse_candidates:
                surviving = [converse_candidates[0]]
                promoted_converse = True
            else:
                # Synthesize a converse candidate from failure summaries
                failure_summaries = []
                for v in validations:
                    if not v.passed:
                        for f in v.failures:
                            failure_summaries.append(f)
                reasoning = (
                    " ".join(failure_summaries)
                    + " Asking for the missing information before proceeding."
                )
                synthesized = CandidateAction(
                    tool_name=CONVERSE_TOOL_NAME,
                    parameters={},
                    reasoning=reasoning,
                    expected_outcome="Ask user for missing required information.",
                )
                surviving = [synthesized]
                promoted_converse = True
        else:
            # Only converse candidates (no non-converse to validate)
            surviving = converse_candidates
            promoted_converse = False

        result = GateResult(
            original_candidates=list(proposal.candidates),
            surviving_candidates=surviving,
            validations=validations,
            promoted_converse=promoted_converse,
        )

        total = len(proposal.candidates)
        passed = sum(1 for v in validations if v.passed)
        logger.info(
            "Parameter gate: %d/%d candidates passed, promoted_converse=%s",
            passed,
            total,
            promoted_converse,
        )

        return result

    def _validate_candidate(self, candidate: CandidateAction) -> ParameterValidation:
        """Validate a single candidate's parameters against its tool schema."""
        tool = self.tool_registry.get(candidate.tool_name)
        if tool is None:
            # Unknown tool — don't block, that's the executor's job
            return ParameterValidation(candidate=candidate, passed=True)

        schema = tool.parameters
        required_fields = schema.get("required", [])
        failures: list[str] = []

        for field_name in required_fields:
            if field_name not in candidate.parameters or candidate.parameters[field_name] is None:
                failures.append(f"{candidate.tool_name} requires {field_name} but it is missing.")
                continue

            value = candidate.parameters[field_name]
            if isinstance(value, str):
                stripped = value.strip()
                if stripped == "":
                    failures.append(f"{field_name}: required but received empty value.")
                elif stripped.lower() in self.placeholders:
                    failures.append(
                        f"{candidate.tool_name} requires {field_name} but received placeholder '{value}'."
                    )

        return ParameterValidation(
            candidate=candidate,
            passed=len(failures) == 0,
            failures=failures,
        )
