#!/usr/bin/env python3
"""
Test client for SigNoz Custom MCP Server
Invokes get_recent_traces, get_recent_logs, and get_metric_anomalies.
"""

import sys
import os
import asyncio
from typing import Any

# Add src to python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.mcp_server import get_recent_traces, get_recent_logs, get_metric_anomalies


def main():
    print("==========================================")
    print("Testing SigNoz Custom MCP Server Tools")
    print("==========================================")

    # 1. Test get_recent_traces
    print("\n--- 1. Testing get_recent_traces('frontend', time_range='15m', limit=3) ---")
    traces_res = get_recent_traces(service_name="frontend", time_range="15m", limit=3)
    print(traces_res[:1000])

    # 2. Test get_recent_logs
    print("\n--- 2. Testing get_recent_logs('frontend', time_range='15m', limit=3) ---")
    logs_res = get_recent_logs(service_name="frontend", time_range="15m", limit=3)
    print(logs_res[:1000])

    # 3. Test get_metric_anomalies
    print("\n--- 3. Testing get_metric_anomalies(service_name='checkout') ---")
    anomalies_res = get_metric_anomalies(service_name="checkout", time_range="1h")
    print(anomalies_res[:1000])

    print("\n--- 4. Testing get_metric_anomalies for all services ---")
    all_anomalies_res = get_metric_anomalies(service_name="", time_range="1h")
    print(all_anomalies_res[:1500])

    print("\n==========================================")
    print("All MCP server tool tests completed successfully!")
    print("==========================================")


if __name__ == "__main__":
    main()
