import json
import logging

from sophia.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registers, lists, and dispatches tools by name. Scoped by active hat."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        logger.info("Registering tool: %s", tool.name)
        self._tools[tool.name] = tool

    def clear(self) -> None:
        """Deregister all tools (used when switching hats)."""
        logger.info("Clearing all registered tools (%d)", len(self._tools))
        self._tools.clear()

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    async def execute(self, tool_name: str, params: dict) -> ToolResult:
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                data=None,
                message=f"Unknown tool: {tool_name}",
            )
        logger.info("Executing tool: %s with params: %s", tool_name, params)
        return await tool.execute(params)

    def get_definitions(self) -> list[dict]:
        """Return all tool definitions as a list of dicts."""
        return [tool.to_definition() for tool in self._tools.values()]

    def get_definitions_text(self) -> str:
        """Return all tool definitions as formatted text for LLM prompts."""
        return json.dumps(self.get_definitions(), indent=2)
