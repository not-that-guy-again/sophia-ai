from dataclasses import dataclass, field


@dataclass
class MCPToolDefinition:
    name: str
    description: str
    input_schema: dict


@dataclass
class MCPToolResult:
    content: list[dict]  # MCP content blocks [{type: "text", text: "..."}, ...]
    is_error: bool = False


@dataclass
class MCPServerInfo:
    name: str
    url: str
    tools: list[MCPToolDefinition] = field(default_factory=list)
