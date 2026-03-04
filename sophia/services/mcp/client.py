import asyncio
import logging
from collections.abc import Callable

import httpx

from sophia.services.mcp.exceptions import (
    MCPConnectionError,
    MCPToolNotFoundError,
    MCPTimeoutError,
)
from sophia.services.mcp.models import MCPServerInfo, MCPToolDefinition, MCPToolResult

logger = logging.getLogger(__name__)

_CLIENT_PROTOCOL_VERSION = "2024-11-05"


class MCPClient:
    """HTTP-based MCP client using JSON-RPC over HTTP."""

    def __init__(
        self,
        server_url: str,
        server_name: str,
        auth_headers: dict | None = None,
        timeout: float = 30.0,
        token_provider: Callable[[], str] | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 0.5,
    ):
        self.server_url = server_url.rstrip("/")
        self.server_name = server_name
        self.timeout = timeout
        self._token_provider = token_provider
        self._static_auth_headers = auth_headers or {}
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._tools: dict[str, MCPToolDefinition] = {}
        self._connected = False
        self._http_client: httpx.AsyncClient | None = None
        self._request_id = 0

    @property
    def auth_headers(self) -> dict:
        if self._token_provider is not None:
            return {"Authorization": f"Bearer {self._token_provider()}"}
        return dict(self._static_auth_headers)

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

    async def _send_jsonrpc(
        self, method: str, params: dict | None = None, *, _reconnect: bool = True
    ) -> dict:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            if attempt > 0:
                if _reconnect and not self._connected:
                    logger.info(
                        "Reconnecting to %s before retry %d/%d",
                        self.server_name,
                        attempt + 1,
                        self._max_retries,
                    )
                    try:
                        await self.connect()
                    except (MCPConnectionError, MCPTimeoutError):
                        pass  # will retry the original call anyway
                delay = self._retry_base_delay * (2 ** (attempt - 1))
                logger.info(
                    "Retrying %s on %s (attempt %d/%d, delay %.1fs)",
                    method,
                    self.server_name,
                    attempt + 1,
                    self._max_retries,
                    delay,
                )
                await asyncio.sleep(delay)

            client = await self._ensure_client()
            payload = self._build_jsonrpc(method, params)
            try:
                response = await client.post("/", json=payload)
                response.raise_for_status()
                data = response.json()
            except httpx.TimeoutException as exc:
                last_exc = MCPTimeoutError(
                    f"Timeout calling {method} on {self.server_name}"
                )
                last_exc.__cause__ = exc
                self._connected = False
                continue
            except (httpx.ConnectError, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_exc = MCPConnectionError(
                    f"Connection error calling {method} on {self.server_name}: {exc}"
                )
                last_exc.__cause__ = exc
                self._connected = False
                continue

            if "error" in data:
                error = data["error"]
                raise MCPConnectionError(
                    f"JSON-RPC error from {self.server_name}: "
                    f"[{error.get('code')}] {error.get('message')}"
                )
            return data.get("result", {})

        raise last_exc  # type: ignore[misc]

    async def connect(self) -> MCPServerInfo:
        """Connect to the MCP server and discover available tools."""
        try:
            init_result = await self._send_jsonrpc("initialize", {
                "protocolVersion": _CLIENT_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "sophia", "version": "0.1.0"},
            }, _reconnect=False)
        except (MCPConnectionError, MCPTimeoutError):
            raise
        except Exception as exc:
            raise MCPConnectionError(
                f"Failed to initialize connection to {self.server_name}: {exc}"
            ) from exc

        server_version = init_result.get("protocolVersion")
        if server_version and server_version != _CLIENT_PROTOCOL_VERSION:
            logger.warning(
                "MCP server %s reports protocolVersion %s, client sent %s",
                self.server_name,
                server_version,
                _CLIENT_PROTOCOL_VERSION,
            )

        result = await self._send_jsonrpc("tools/list", _reconnect=False)
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
