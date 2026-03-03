import json
import logging
import uuid
from datetime import UTC, datetime

from sophia.core.input_gate import _extract_json
from sophia.hats.prompt_assembler import assemble_prompt
from sophia.hats.schema import HatConfig
from sophia.llm.provider import LLMProvider
from sophia.llm.prompts.core.memory_extract import MEMORY_EXTRACT_SYSTEM_PROMPT
from sophia.memory.models import Entity, Episode, Relationship
from sophia.memory.provider import MemoryProvider

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """Extracts structured memory from completed conversations via LLM.

    After a pipeline run completes, this component:
    1. Calls the LLM to extract episode summary, entities, and relationships
    2. Stores the episode (Tier 2)
    3. Stores/updates entities and relationships (Tier 3)
    """

    def __init__(
        self,
        llm: LLMProvider,
        memory: MemoryProvider,
        hat_config: HatConfig | None = None,
    ):
        self.llm = llm
        self.memory = memory
        self.hat_config = hat_config

    def _get_domain_context(self) -> str:
        if self.hat_config and self.hat_config.prompts.get("system"):
            return f"## Domain Context ({self.hat_config.display_name})\n\n{self.hat_config.prompts['system']}"
        return ""

    async def extract_and_store(
        self,
        user_message: str,
        action_taken: str,
        action_parameters: dict,
        outcome: str,
        conversation_id: str | None = None,
    ) -> Episode:
        """Extract memory from a completed conversation and persist it."""
        conversation_id = conversation_id or uuid.uuid4().hex[:12]
        hat_name = self.hat_config.name if self.hat_config else "none"

        core_prompt = MEMORY_EXTRACT_SYSTEM_PROMPT.format(
            hat_name=hat_name,
            user_message=user_message,
            action_taken=action_taken,
            action_parameters=json.dumps(action_parameters, default=str),
            outcome=outcome,
            domain_context=self._get_domain_context(),
        )
        system_prompt = assemble_prompt("memory_extract", core_prompt, self.hat_config)

        response = await self.llm.complete(
            system_prompt=system_prompt,
            user_message=user_message,
            response_format={"type": "json"},
        )

        logger.debug("Memory extractor raw response: %s", response.content)

        parsed = json.loads(_extract_json(response.content))

        # Build and store episode (Tier 2)
        ep_data = parsed.get("episode", {})
        entity_names = [e.get("name", "") for e in parsed.get("entities", [])]

        episode = Episode(
            id=f"ep_{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(UTC),
            conversation_id=conversation_id,
            participants=ep_data.get("participants", []),
            summary=ep_data.get("summary", ""),
            actions_taken=ep_data.get("actions_taken", []),
            outcome=ep_data.get("outcome", ""),
            entities_referenced=entity_names,
            hat_name=hat_name,
        )
        await self.memory.store_episode(episode)
        logger.info("Stored episode %s (conversation=%s)", episode.id, conversation_id)

        # Store entities (Tier 3)
        for ent_data in parsed.get("entities", []):
            entity = Entity(
                id=f"ent_{uuid.uuid4().hex[:8]}",
                entity_type=ent_data.get("entity_type", ""),
                name=ent_data.get("name", ""),
                attributes=ent_data.get("attributes", {}),
            )
            await self.memory.store_entity(entity)
            logger.info("Stored entity %s: %s (%s)", entity.id, entity.name, entity.entity_type)

        # Store relationships (Tier 3)
        for rel_data in parsed.get("relationships", []):
            relationship = Relationship(
                id=f"rel_{uuid.uuid4().hex[:8]}",
                from_entity=rel_data.get("from_entity", ""),
                relation=rel_data.get("relation", ""),
                to_entity=rel_data.get("to_entity", ""),
                metadata=rel_data.get("metadata", {}),
            )
            await self.memory.store_relationship(relationship)
            logger.info(
                "Stored relationship %s: %s -[%s]-> %s",
                relationship.id,
                relationship.from_entity,
                relationship.relation,
                relationship.to_entity,
            )

        return episode
