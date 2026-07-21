#!/usr/bin/env python3
"""
SigNoz Direct JSON-RPC MCP Client

Provides direct JSON-RPC HTTP calls to the SigNoz MCP server running in Docker (http://localhost:8000/mcp).
Supports both JWT access token authentication and SIGNOZ-API-KEY header authentication.
"""

import json
import os
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

SIGNOZ_BASE_URL = os.getenv("SIGNOZ_BASE_URL", "http://localhost:8080")
SIGNOZ_MCP_URL = os.getenv("SIGNOZ_MCP_URL", "http://localhost:8000/mcp")
SIGNOZ_EMAIL = os.getenv("SIGNOZ_EMAIL", "vaishnav.verma.cs28@iilm.edu")
SIGNOZ_PASSWORD = os.getenv("SIGNOZ_PASSWORD", "password")
SIGNOZ_ORG_ID = os.getenv("SIGNOZ_ORG_ID", "019f8442-98bb-7410-a3fb-1183140fa210")
SIGNOZ_API_KEY = os.getenv("SIGNOZ_API_KEY", "")


class SigNozDirectMCPClient:
    """
    Client for calling SigNoz MCP server tools using direct JSON-RPC HTTP requests.
    """

    def __init__(self, mcp_url: str = SIGNOZ_MCP_URL, api_key: str = SIGNOZ_API_KEY):
        self.mcp_url = mcp_url
        self.api_key = api_key
        self.access_token: Optional[str] = None

    def login(self) -> str:
        """Authenticate with SigNoz API v2 to get a Bearer access token."""
        url = f"{SIGNOZ_BASE_URL}/api/v2/sessions/email_password"
        payload = json.dumps({
            "email": SIGNOZ_EMAIL,
            "password": SIGNOZ_PASSWORD,
            "orgID": SIGNOZ_ORG_ID
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            headers={"Content-Type": "application/json"},
            data=payload
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.access_token = data.get("data", {}).get("accessToken")
                return self.access_token
        except Exception as e:
            raise RuntimeError(f"Failed to authenticate with SigNoz at {url}: {e}")

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executes a direct JSON-RPC HTTP call to the SigNoz MCP server.

        POST /mcp
        Headers:
          Authorization: Bearer <token> OR SIGNOZ-API-KEY: <key>
          Content-Type: application/json
        
        Payload:
        {
          "jsonrpc": "2.0",
          "id": 1,
          "method": "tools/call",
          "params": {
            "name": tool_name,
            "arguments": arguments or {}
          }
        }
        """
        if arguments is None:
            arguments = {}

        # Use API key header if configured, otherwise fall back to Bearer token login
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["SIGNOZ-API-KEY"] = self.api_key
        else:
            if not self.access_token:
                self.login()
            headers["Authorization"] = f"Bearer {self.access_token}"

        def _exec_rpc():
            body = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            req = urllib.request.Request(
                self.mcp_url,
                headers=headers,
                data=json.dumps(body).encode("utf-8")
            )
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))

        try:
            return _exec_rpc()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and not self.api_key:
                # Refresh session token once on auth failure
                self.login()
                headers["Authorization"] = f"Bearer {self.access_token}"
                return _exec_rpc()
            raise

    # Alias for backward compatibility
    call_mcp_tool = call_tool


# Default global instance
default_mcp_client = SigNozDirectMCPClient()


def call_mcp_tool_direct(tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Convenience helper to invoke any SigNoz MCP tool via direct JSON-RPC HTTP call."""
    return default_mcp_client.call_tool(tool_name, arguments)
