import logging

import httpx

from sophia.services.mcp.exceptions import (
    MCPConnectionError,
    MCPToolNotFoundError,
    MCPTimeoutError,
)
from sophia.services.mcp.models import MCPServerInfo, MCPToolDefinition, MCPToolResult

logger = logging.getLogger(__name__)


class MCPClient:
    """HTTP-based MCP client using JSON-RPC over HTTP."""

    def __init__(
        self,
        server_url: str,
        server_name: str,
        auth_headers: dict | None = None,
        timeout: float = 30.0,
    ):
        self.server_url = server_url.rstrip("/")
        self.server_name = server_name
        self.auth_headers = auth_headers or {}
        self.timeout = timeout
        self._tools: dict[str, MCPToolDefinition] = {}
        self._connected = False
        self._http_client: httpx.AsyncClient | None = None
        self._request_id = 0

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _build_jsonrpc(self, method: str, params: dict | None = None) -> dict:
        msg = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": method,
        }
        if params is not None:
            msg["params"] = params
        return msg

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url=self.server_url,
                headers=self.auth_headers,
                timeout=self.timeout,
            )
        return self._http_client

    async def _send_jsonrpc(self, method: str, params: dict | None = None) -> dict:
        client = await self._ensure_client()
        payload = self._build_jsonrpc(method, params)
        try:
            response = await client.post("/", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise MCPTimeoutError(
                f"Timeout calling {method} on {self.server_name}"
            ) from exc
        except (httpx.ConnectError, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            raise MCPConnectionError(
                f"Connection error calling {method} on {self.server_name}: {exc}"
            ) from exc

        if "error" in data:
            error = data["error"]
            raise MCPConnectionError(
                f"JSON-RPC error from {self.server_name}: "
                f"[{error.get('code')}] {error.get('message')}"
            )
        return data.get("result", {})

    async def connect(self) -> MCPServerInfo:
        """Connect to the MCP server and discover available tools."""
        try:
            await self._send_jsonrpc("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "sophia", "version": "0.1.0"},
            })
        except (MCPConnectionError, MCPTimeoutError):
            raise
        except Exception as exc:
            raise MCPConnectionError(
                f"Failed to initialize connection to {self.server_name}: {exc}"
            ) from exc

        result = await self._send_jsonrpc("tools/list")
        tools_data = result.get("tools", [])

        self._tools.clear()
        tool_list = []
        for t in tools_data:
            tool_def = MCPToolDefinition(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            )
            self._tools[tool_def.name] = tool_def
            tool_list.append(tool_def)

        self._connected = True
        logger.info(
            "Connected to MCP server %s (%s), discovered %d tools",
            self.server_name,
            self.server_url,
            len(tool_list),
        )

        return MCPServerInfo(
            name=self.server_name,
            url=self.server_url,
            tools=tool_list,
        )

    async def call_tool(self, tool_name: str, arguments: dict) -> MCPToolResult:
        """Call an MCP tool by name."""
        if tool_name not in self._tools:
            raise MCPToolNotFoundError(
                f"Tool '{tool_name}' not found on server {self.server_name}. "
                f"Available tools: {sorted(self._tools.keys())}"
            )

        result = await self._send_jsonrpc("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

        content = result.get("content", [])
        is_error = result.get("isError", False)
        return MCPToolResult(content=content, is_error=is_error)

    async def list_tools(self) -> list[MCPToolDefinition]:
        """Return discovered tools. Must call connect() first."""
        return list(self._tools.values())

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
        self._http_client = None
        self._connected = False
        logger.info("Closed MCP client for %s", self.server_name)

    @property
    def is_connected(self) -> bool:
        return self._connected
