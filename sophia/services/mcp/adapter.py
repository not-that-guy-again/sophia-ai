import logging

from sophia.services.mcp.client import MCPClient
from sophia.services.mcp.models import MCPToolResult

logger = logging.getLogger(__name__)


class MCPServiceAdapter:
    """Base class for MCP-backed service implementations.

    Subclasses define a tool_mapping dict that maps service method names
    to MCP tool configurations:
    {
        "method_name": {
            "tool_name": "mcp_tool_name",
            "build_args": callable(**kwargs) -> dict,
            "parse_response": callable(MCPToolResult) -> dataclass,
        }
    }
    """

    def __init__(self, client: MCPClient, tool_mapping: dict):
        self.client = client
        self.mapping = tool_mapping

    async def _call(self, method_name: str, **kwargs):
        """Generic method to call an MCP tool via the mapping."""
        config = self.mapping.get(method_name)
        if not config:
            raise NotImplementedError(
                f"Method '{method_name}' has no MCP tool mapping"
            )
        args = config["build_args"](**kwargs)
        result = await self.client.call_tool(config["tool_name"], args)
        if result.is_error:
            return config.get("error_handler", self._default_error_handler)(result)
        return config["parse_response"](result)

    def _default_error_handler(self, result: MCPToolResult) -> None:
        text = ""
        if result.content:
            text = result.content[0].get("text", "")
        logger.warning("MCP tool returned error: %s", text)
        return None

    def validate_mapping(self) -> list[str]:
        """Check that all mapped tools exist on the server.
        Returns list of missing tool names."""
        available = {t.name for t in self.client._tools.values()}
        mapped = {cfg["tool_name"] for cfg in self.mapping.values()}
        return sorted(mapped - available)
