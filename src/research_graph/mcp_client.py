"""MCP (Model Context Protocol) client stub for ResearchGraph.

This module provides a standard interface for agents to call external MCP
servers (filesystem, GitHub, SQLite, web search, etc.) without needing custom
tool wrappers for every new API.

Current state: protocol-ready stub. All calls are logged and return structured
errors so the pipeline degrades gracefully. Wire real MCP servers by registering
them via MCPClient.register().

MCP reference: https://modelcontextprotocol.io/

Usage:
    client = MCPClient()
    client.register("filesystem", base_url="http://localhost:3000")
    result = client.call_tool("filesystem", "read_file", {"path": "/tmp/paper.txt"})
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


@dataclass
class MCPToolResult:
    success: bool
    data: Any
    error: str = ""
    server: str = ""
    tool: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "server": self.server,
            "tool": self.tool,
        }


@dataclass
class MCPServer:
    name: str
    base_url: str
    transport: str = "http"   # "http" | "stdio"
    capabilities: List[str] = field(default_factory=list)
    enabled: bool = True


class MCPClient:
    """Protocol-ready MCP client. Registers servers and routes tool calls."""

    def __init__(self) -> None:
        self._servers: Dict[str, MCPServer] = {}
        self._call_log: List[dict] = []
        self._register_builtin_stubs()

    def register(
        self,
        name: str,
        base_url: str,
        transport: str = "http",
        capabilities: Optional[List[str]] = None,
    ) -> None:
        self._servers[name] = MCPServer(
            name=name,
            base_url=base_url,
            transport=transport,
            capabilities=capabilities or [],
        )
        logger.info("MCP server registered: %s @ %s", name, base_url)

    def call_tool(
        self,
        server_name: str,
        tool_name: str,
        params: Dict[str, Any],
        timeout: int = 15,
    ) -> MCPToolResult:
        """Call a tool on a registered MCP server.

        If the server is not registered or the call fails, returns a structured
        error result so the pipeline can fall back gracefully.
        """
        log_entry = {"server": server_name, "tool": tool_name, "params_keys": list(params.keys())}

        server = self._servers.get(server_name)
        if server is None or not server.enabled:
            result = MCPToolResult(
                success=False,
                data=None,
                error=f"MCP server '{server_name}' is not registered or disabled.",
                server=server_name,
                tool=tool_name,
            )
            log_entry["status"] = "no_server"
            self._call_log.append(log_entry)
            return result

        try:
            result = self._http_call(server, tool_name, params, timeout)
        except Exception as exc:
            result = MCPToolResult(
                success=False,
                data=None,
                error=str(exc),
                server=server_name,
                tool=tool_name,
            )

        log_entry["status"] = "success" if result.success else "error"
        log_entry["error"] = result.error
        self._call_log.append(log_entry)
        return result

    def list_tools(self, server_name: str) -> MCPToolResult:
        """Fetch available tools from a registered MCP server."""
        return self.call_tool(server_name, "__list_tools__", {})

    def call_log(self) -> List[dict]:
        return list(self._call_log)

    def _http_call(
        self,
        server: MCPServer,
        tool_name: str,
        params: Dict[str, Any],
        timeout: int,
    ) -> MCPToolResult:
        payload = json.dumps({"tool": tool_name, "params": params}).encode()
        req = Request(
            f"{server.base_url.rstrip('/')}/tools/{tool_name}",
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "ResearchGraph/1.0"},
            method="POST",
        )
        with urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
        return MCPToolResult(
            success=True,
            data=body,
            server=server.name,
            tool=tool_name,
        )

    def _register_builtin_stubs(self) -> None:
        """Pre-register well-known MCP server stubs (disabled by default).
        Enable them by calling client.register() with a real base_url.
        """
        for name, url in [
            ("filesystem", "http://localhost:3001"),
            ("github", "http://localhost:3002"),
            ("sqlite", "http://localhost:3003"),
            ("web-search", "http://localhost:3004"),
        ]:
            self._servers[name] = MCPServer(
                name=name,
                base_url=url,
                capabilities=[name],
                enabled=False,  # disabled until explicitly registered
            )


# Module-level singleton for use across the pipeline
_default_client: Optional[MCPClient] = None


def get_mcp_client() -> MCPClient:
    global _default_client
    if _default_client is None:
        _default_client = MCPClient()
    return _default_client
