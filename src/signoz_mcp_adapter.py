"""
SigNoz MCP Adapter

Deep adapter around SigNoz's prebuilt MCP server (JSON-RPC over HTTP).
This module is the *only* place in PatchNoz that knows SigNoz's native MCP
tool names, its JSON-RPC envelope, and its auth flow. Everything else in
PatchNoz talks to a small, tool-oriented interface instead.

PatchNoz does not run its own MCP server as the source of truth here -
this adapter is a thin client of SigNoz's own MCP server on :8000/mcp.
"""

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from src.env import load_env
from src.self_telemetry import start_span

load_env()

SIGNOZ_BASE_URL = os.getenv("SIGNOZ_BASE_URL", "http://localhost:8080")
SIGNOZ_MCP_URL = os.getenv("SIGNOZ_MCP_URL", "http://localhost:8000/mcp")
SIGNOZ_API_KEY = os.getenv("SIGNOZ_API_KEY", "")
SIGNOZ_EMAIL = os.getenv("SIGNOZ_EMAIL", "")
SIGNOZ_PASSWORD = os.getenv("SIGNOZ_PASSWORD", "")
SIGNOZ_ORG_ID = os.getenv("SIGNOZ_ORG_ID", "")


class SigNozMCPAdapter:
    """Adapter for interacting with SigNoz's prebuilt MCP server via JSON-RPC over HTTP."""

    def __init__(
        self,
        mcp_url: str = SIGNOZ_MCP_URL,
        base_url: str = SIGNOZ_BASE_URL,
        api_key: str = SIGNOZ_API_KEY,
        email: str = SIGNOZ_EMAIL,
        password: str = SIGNOZ_PASSWORD,
        org_id: str = SIGNOZ_ORG_ID,
    ):
        self.mcp_url = mcp_url
        self.base_url = base_url
        self.api_key = api_key
        self.email = email
        self.password = password
        self.org_id = org_id
        self.access_token: Optional[str] = None

    # --- Public MCP interface ---

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Calls a native SigNoz MCP tool by name and returns its parsed JSON result."""
        arguments = arguments or {}
        with start_span("patchnoz.signoz_mcp.call", {"mcp.tool": tool_name}) as span:
            try:
                response = self._call_rpc(tool_name, arguments)
                result = self._parse_result(response)
                span.set_attribute("mcp.success", True)
                return result
            except Exception as e:
                span.set_attribute("mcp.success", False)
                span.record_exception(e)
                raise

    def list_services(self) -> Dict[str, Any]:
        """Calls native tool 'signoz_list_services'."""
        return self.call_tool("signoz_list_services", {})

    def search_traces(self, service: str, limit: int = 5) -> Dict[str, Any]:
        """Calls native tool 'signoz_search_traces'."""
        return self.call_tool("signoz_search_traces", {"service": service, "limit": limit})

    def search_logs(self, service: str, limit: int = 10) -> Dict[str, Any]:
        """Calls native tool 'signoz_search_logs'."""
        return self.call_tool("signoz_search_logs", {"service": service, "limit": limit})

    def list_alerts(self) -> Dict[str, Any]:
        """Calls native tool 'signoz_list_alerts'."""
        return self.call_tool("signoz_list_alerts", {})

    @staticmethod
    def _parse_firing_alerts(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract a flat list of alert dicts from signoz_list_alerts response."""
        if not isinstance(raw, dict):
            return []
        data = raw.get("data")
        if data is None:
            data = raw

        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]

        if isinstance(data, dict):
            alerts = data.get("alerts")
            if alerts is None:
                alerts = data.get("data")
            if isinstance(alerts, list):
                return [item for item in alerts if isinstance(item, dict)]
            if isinstance(alerts, dict):
                return [alerts]
            if any(k in data for k in ("name", "alertname", "state", "labels")):
                return [data]

        return []

    def list_firing_alerts(self) -> List[Dict[str, Any]]:
        """
        Calls signoz_list_alerts, normalizes payload shapes, and returns raw alert dicts
        that are currently in a firing or active state.
        """
        raw = self.list_alerts()
        alerts = self._parse_firing_alerts(raw)
        firing = []
        for a in alerts:
            if not isinstance(a, dict):
                continue
            state = a.get("state")
            state_str = str(state if state is not None else "").lower()
            if state_str in ("firing", "alerting", "active", ""):
                firing.append(a)
        return firing

    # --- Transport & auth internals ---

    def _login(self) -> str:
        """Authenticates against SigNoz API v2 to obtain a bearer access token."""
        url = f"{self.base_url}/api/v2/sessions/email_password"
        payload = json.dumps({
            "email": self.email,
            "password": self.password,
            "orgID": self.org_id,
        }).encode("utf-8")
        req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, data=payload)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"SigNoz login failed against {url}: {e}") from e

        token = data.get("data", {}).get("accessToken")
        if not token:
            raise RuntimeError(f"SigNoz login response missing accessToken: {data}")
        self.access_token = token
        return token

    def _auth_headers(self) -> Dict[str, str]:
        if self.api_key:
            return {"SIGNOZ-API-KEY": self.api_key}
        if not self.access_token:
            if not (self.email and self.password and self.org_id):
                raise RuntimeError(
                    "No SigNoz MCP credentials configured. Set SIGNOZ_API_KEY, or all of "
                    "SIGNOZ_EMAIL, SIGNOZ_PASSWORD, and SIGNOZ_ORG_ID."
                )
            self._login()
        return {"Authorization": f"Bearer {self.access_token}"}

    def _call_rpc(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json", **self._auth_headers()}
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }).encode("utf-8")

        def _do_request(hdrs: Dict[str, str]) -> Dict[str, Any]:
            req = urllib.request.Request(self.mcp_url, headers=hdrs, data=body)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))

        try:
            return _do_request(headers)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and not self.api_key:
                self._login()
                headers["Authorization"] = f"Bearer {self.access_token}"
                return _do_request(headers)
            raise RuntimeError(f"SigNoz MCP call to '{tool_name}' failed: HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"SigNoz MCP call to '{tool_name}' failed: {e}") from e

    @staticmethod
    def _parse_result(response: Dict[str, Any]) -> Dict[str, Any]:
        """Extracts and parses the JSON text SigNoz MCP nests in result.content[0].text."""
        if "error" in response:
            raise RuntimeError(f"SigNoz MCP tool error: {response['error']}")

        content = response.get("result", {}).get("content", [])
        if not content:
            return {}
        raw_text = content[0].get("text", "")
        if not raw_text:
            return {}
        try:
            parsed = json.loads(raw_text)
        except (json.JSONDecodeError, TypeError):
            return {"raw": raw_text}
        return parsed if isinstance(parsed, dict) else {"data": parsed}


# Global default adapter instance, shared unless a caller needs a custom one.
default_adapter = SigNozMCPAdapter()
