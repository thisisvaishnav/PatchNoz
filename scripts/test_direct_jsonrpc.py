#!/usr/bin/env python3
"""
Test script for direct JSON-RPC HTTP calls to SigNoz MCP Server.
Demonstrates calling native tools (e.g. signoz_list_services, signoz_search_traces, signoz_list_alerts).
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.mcp_client import call_mcp_tool_direct, SigNozDirectMCPClient


def main():
    print("==========================================")
    print("Testing Direct JSON-RPC Calls to SigNoz MCP (:8000/mcp)")
    print("==========================================")

    # 1. Direct JSON-RPC call to list services
    print("\n[1] Calling 'signoz_list_services' via JSON-RPC...")
    resp_services = call_mcp_tool_direct("signoz_list_services", {})
    print("Response:")
    print(json.dumps(resp_services, indent=2)[:800])

    # 2. Direct JSON-RPC call to search traces
    print("\n[2] Calling 'signoz_search_traces' for service='checkout'...")
    resp_traces = call_mcp_tool_direct("signoz_search_traces", {
        "service": "checkout",
        "limit": 3
    })
    print("Response:")
    print(json.dumps(resp_traces, indent=2)[:800])

    # 3. Direct JSON-RPC call to list active alerts
    print("\n[3] Calling 'signoz_list_alerts'...")
    resp_alerts = call_mcp_tool_direct("signoz_list_alerts", {})
    print("Response:")
    print(json.dumps(resp_alerts, indent=2)[:800])

    print("\n==========================================")
    print("Direct JSON-RPC calls completed successfully!")
    print("==========================================")


if __name__ == "__main__":
    main()
