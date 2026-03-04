class MCPError(Exception):
    """Base exception for MCP operations."""


class MCPConnectionError(MCPError):
    """Raised when connection to MCP server fails."""


class MCPTimeoutError(MCPError):
    """Raised when MCP server response exceeds timeout."""


class MCPToolNotFoundError(MCPError):
    """Raised when a requested tool is not available on the server."""


class MCPParseError(MCPError):
    """Raised when MCP response cannot be parsed."""
