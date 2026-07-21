"""
SigNoz Direct MCP Client (Compatibility Module)

Re-exports SigNozMCPAdapter from src.signoz_mcp_adapter for backward compatibility.
"""

from src.signoz_mcp_adapter import (
    SigNozMCPAdapter as SigNozDirectMCPClient,
    SIGNOZ_BASE_URL,
    SIGNOZ_MCP_URL,
    SIGNOZ_EMAIL,
    SIGNOZ_PASSWORD,
    SIGNOZ_ORG_ID,
    SIGNOZ_API_KEY,
    default_adapter as default_mcp_client,
)


def call_mcp_tool_direct(tool_name: str, arguments=None):
    """Convenience helper for backward compatibility."""
    return default_mcp_client.call_tool(tool_name, arguments)
