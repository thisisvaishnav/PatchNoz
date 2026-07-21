"""
SigNoz MCP Adapter

Encapsulates direct JSON-RPC HTTP communications with SigNoz prebuilt MCP server.
Isolates all native SigNoz MCP tool names (e.g. signoz_search_traces, signoz_list_services,
signoz_search_logs) and response parsing in a single module for high locality.
"""

import json
import os
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional

SIGNOZ_BASE_URL = os.getenv("SIGNOZ_BASE_URL", "http://localhost:8080")
SIGNOZ_MCP_URL = os.getenv("SIGNOZ_MCP_URL", "http://localhost:8000/mcp")
SIGNOZ_EMAIL = os.getenv("SIGNOZ_EMAIL", "vaishnav.verma.cs28@iilm.edu")
SIGNOZ_PASSWORD = os.getenv("SIGNOZ_PASSWORD", "password")
SIGNOZ_ORG_ID = os.getenv("SIGNOZ_ORG_ID", "019f8442-98bb-7410-a3fb-1183140fa210")
SIGNOZ_API_KEY = os.getenv("SIGNOZ_API_KEY", "")


class SigNozMCPAdapter:
    """
    Adapter for interacting with SigNoz prebuilt MCP Server via direct JSON-RPC HTTP.
    Encapsulates native tool names and response parsing details.
    """

    def __init__(self, mcp_url: str = SIGNOZ_MCP_URL, api_key: str = SIGNOZ_API_KEY, base_url: str = SIGNOZ_BASE_URL):
        self.mcp_url = mcp_url
        self.api_key = api_key
        self.base_url = base_url
        self.access_token: Optional[str] = None

    def login(self) -> str:
        """Authenticate with SigNoz API v2 to get a Bearer access token."""
        url = f"{self.base_url}/api/v2/sessions/email_password"
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
                return self.access_token or ""
        except Exception as e:
            raise RuntimeError(f"Failed to authenticate with SigNoz at {url}: {e}")

    def call_mcp_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executes a direct JSON-RPC HTTP call to the SigNoz MCP server.
        """
        if arguments is None:
            arguments = {}

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
                self.login()
                headers["Authorization"] = f"Bearer {self.access_token}"
                return _exec_rpc()
            raise

    def _parse_mcp_result_json(self, response: Dict[str, Any]) -> Any:
        """Helper to extract and parse JSON text inside MCP result.content[0].text."""
        content = response.get("result", {}).get("content", [])
        if not content:
            return None
        raw_text = content[0].get("text", "")
        if not raw_text:
            return None
        try:
            return json.loads(raw_text)
        except Exception:
            return raw_text

    # --- Native SigNoz MCP Tool Wrappers ---

    def search_traces(self, service: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Invokes native tool 'signoz_search_traces'."""
        response = self.call_mcp_tool("signoz_search_traces", {
            "service": service,
            "limit": limit
        })
        parsed = self._parse_mcp_result_json(response)
        if not isinstance(parsed, dict):
            return []

        results = parsed.get("data", {}).get("data", {}).get("results", [])
        if not results or not results[0].get("rows"):
            return []

        rows = results[0]["rows"]
        traces = []
        for row in rows:
            data = row.get("data", {})
            trace_id = data.get("trace_id")
            span_id = data.get("span_id")
            name = data.get("name")
            has_error = data.get("has_error", False)
            duration_ms = round(data.get("duration_nano", 0) / 1e6, 2)
            timestamp = data.get("timestamp")
            status_code = data.get("status_code_string", "Unset")
            http_method = data.get("http.request.method") or data.get("rpc.method") or ""

            traces.append({
                "trace_id": trace_id,
                "span_id": span_id,
                "operation": name,
                "method": http_method,
                "duration_ms": duration_ms,
                "has_error": has_error,
                "status": status_code,
                "timestamp": timestamp,
                "web_url": f"{self.base_url}/trace/{trace_id}" if trace_id else ""
            })
        return traces

    def search_logs(self, service: str, limit: int = 20, query: str = "", severity: str = "") -> List[Dict[str, Any]]:
        """Invokes native tool 'signoz_search_logs'."""
        args: Dict[str, Any] = {"service": service, "limit": limit}
        if query:
            args["query"] = query
        if severity:
            args["severity"] = severity

        response = self.call_mcp_tool("signoz_search_logs", args)
        parsed = self._parse_mcp_result_json(response)
        if not isinstance(parsed, dict):
            return []

        results = parsed.get("data", {}).get("data", {}).get("results", [])
        if not results or not results[0].get("rows"):
            return []

        rows = results[0]["rows"]
        logs = []
        for row in rows:
            data = row.get("data", {})
            logs.append({
                "timestamp": data.get("timestamp"),
                "severity": data.get("severity_text") or data.get("severity_number"),
                "body": data.get("body"),
                "trace_id": data.get("trace_id"),
                "span_id": data.get("span_id"),
                "attributes": data.get("attributes")
            })
        return logs

    def list_services(self) -> List[Dict[str, Any]]:
        """Invokes native tool 'signoz_list_services'."""
        response = self.call_mcp_tool("signoz_list_services", {})
        parsed = self._parse_mcp_result_json(response)
        if isinstance(parsed, dict):
            return parsed.get("data", [])
        return []

    def get_top_operations(self, service: str) -> List[Dict[str, Any]]:
        """Invokes native tool 'signoz_get_service_top_operations'."""
        response = self.call_mcp_tool("signoz_get_service_top_operations", {"service": service})
        parsed = self._parse_mcp_result_json(response)
        if isinstance(parsed, list):
            top_ops = []
            for op in parsed:
                top_ops.append({
                    "operation": op.get("name"),
                    "num_calls": op.get("numCalls"),
                    "error_count": op.get("errorCount"),
                    "p50_ms": round(op.get("p50", 0) / 1e6, 2),
                    "p95_ms": round(op.get("p95", 0) / 1e6, 2),
                    "p99_ms": round(op.get("p99", 0) / 1e6, 2)
                })
            return top_ops
        return []

    def list_alerts(self) -> List[Dict[str, Any]]:
        """Invokes native tool 'signoz_list_alerts'."""
        response = self.call_mcp_tool("signoz_list_alerts", {})
        parsed = self._parse_mcp_result_json(response)
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict):
            return parsed.get("data", [])
        return []


# Global default adapter instance
default_adapter = SigNozMCPAdapter()
