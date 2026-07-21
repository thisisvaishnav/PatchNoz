#!/usr/bin/env python3
"""
SigNoz Custom MCP Server

Exposes tools for diagnosing SRE issues via SigNoz:
- get_recent_traces(service_name, time_range, limit)
- get_recent_logs(service_name, time_range, query, severity, limit)
- get_metric_anomalies(service_name, metric_name, time_range)
"""

import json
import os
import time
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP(
    "SigNoz Custom MCP Server",
    instructions="MCP Server providing tools to query traces, logs, and metric anomalies from SigNoz."
)

from src.mcp_client import default_mcp_client as client, SIGNOZ_BASE_URL



@mcp.tool()
def get_recent_traces(service_name: str, time_range: str = "15m", limit: int = 10) -> str:
    """
    Fetch recent traces for a given service and time range.

    Args:
        service_name: Name of the target service (e.g. 'frontend', 'checkout', 'payment').
        time_range: Human readable time range (e.g. '15m', '1h', '24h').
        limit: Max number of traces to return (default 10).

    Returns:
        Formatted summary of recent traces including trace IDs, operation names, durations, errors, and web URLs.
    """
    try:
        response = client.call_mcp_tool("signoz_search_traces", {
            "service": service_name,
            "limit": limit
        })

        result_content = response.get("result", {}).get("content", [])
        if not result_content:
            return f"No trace data returned for service '{service_name}'."

        raw_text = result_content[0].get("text", "")
        parsed = json.loads(raw_text)

        results = parsed.get("data", {}).get("data", {}).get("results", [])
        if not results or not results[0].get("rows"):
            return f"No recent traces found for service '{service_name}' in the last {time_range}."

        rows = results[0]["rows"]
        traces_summary = []
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

            traces_summary.append({
                "trace_id": trace_id,
                "span_id": span_id,
                "operation": name,
                "method": http_method,
                "duration_ms": duration_ms,
                "has_error": has_error,
                "status": status_code,
                "timestamp": timestamp,
                "web_url": f"{SIGNOZ_BASE_URL}/trace/{trace_id}" if trace_id else ""
            })

        return json.dumps({
            "service": service_name,
            "time_range": time_range,
            "total_fetched": len(traces_summary),
            "traces": traces_summary
        }, indent=2)

    except Exception as e:
        return f"Error fetching traces for service '{service_name}': {str(e)}"


@mcp.tool()
def get_recent_logs(service_name: str, time_range: str = "15m", query: str = "", severity: str = "", limit: int = 20) -> str:
    """
    Fetch recent logs for a given service, optionally filtered by search text or severity.

    Args:
        service_name: Name of the target service (e.g. 'frontend', 'checkout').
        time_range: Time window to query (e.g. '15m', '1h').
        query: Optional search text / pattern inside log body.
        severity: Optional log severity filter (e.g. 'ERROR', 'WARN', 'INFO').
        limit: Max number of logs to return (default 20).

    Returns:
        Formatted summary of recent log entries.
    """
    try:
        args: Dict[str, Any] = {
            "service": service_name,
            "limit": limit
        }
        if query:
            args["query"] = query
        if severity:
            args["severity"] = severity

        response = client.call_mcp_tool("signoz_search_logs", args)

        result_content = response.get("result", {}).get("content", [])
        if not result_content:
            return f"No log data returned for service '{service_name}'."

        raw_text = result_content[0].get("text", "")
        parsed = json.loads(raw_text)

        results = parsed.get("data", {}).get("data", {}).get("results", [])
        rows = results[0].get("rows") if results else None

        if not rows:
            return f"No recent logs found for service '{service_name}' (query: '{query}', severity: '{severity}') in the last {time_range}."

        logs_summary = []
        for row in rows:
            data = row.get("data", {})
            logs_summary.append({
                "timestamp": data.get("timestamp"),
                "severity": data.get("severity_text") or data.get("severity_number"),
                "body": data.get("body"),
                "trace_id": data.get("trace_id"),
                "span_id": data.get("span_id"),
                "attributes": data.get("attributes")
            })

        return json.dumps({
            "service": service_name,
            "time_range": time_range,
            "total_fetched": len(logs_summary),
            "logs": logs_summary
        }, indent=2)

    except Exception as e:
        return f"Error fetching logs for service '{service_name}': {str(e)}"


@mcp.tool()
def get_metric_anomalies(service_name: str = "", metric_name: str = "", time_range: str = "1h") -> str:
    """
    Detect metric anomalies, high error rates, latency spikes, or call rate anomalies across services.

    Args:
        service_name: Optional service name to filter (e.g. 'checkout'). If empty, checks all services.
        metric_name: Optional specific metric name to inspect.
        time_range: Time range for evaluation (default '1h').

    Returns:
        Summary of service health metrics, error rates, p99 latency spikes, and top operation bottlenecks.
    """
    try:
        # Fetch high-level service metrics
        services_resp = client.call_mcp_tool("signoz_list_services", {})
        services_content = services_resp.get("result", {}).get("content", [])
        
        services_list = []
        if services_content:
            raw_text = services_content[0].get("text", "")
            services_list = json.loads(raw_text).get("data", [])

        anomalies = []

        for svc in services_list:
            name = svc.get("serviceName")
            if service_name and name.lower() != service_name.lower():
                continue

            error_rate = svc.get("errorRate", 0)
            p99_ms = round(svc.get("p99", 0) / 1e6, 2)
            avg_duration_ms = round(svc.get("avgDuration", 0) / 1e6, 2)
            num_errors = svc.get("numErrors", 0)
            num_calls = svc.get("numCalls", 0)

            # Check if there is an error spike or high latency
            is_error_anomaly = error_rate > 1.0  # >1% error rate
            is_latency_anomaly = p99_ms > 1000.0  # >1s p99 latency

            if is_error_anomaly or is_latency_anomaly or service_name:
                ops_resp = client.call_mcp_tool("signoz_get_service_top_operations", {"service": name})
                ops_content = ops_resp.get("result", {}).get("content", [])
                top_ops = []
                if ops_content:
                    try:
                        ops_data = json.loads(ops_content[0].get("text", "[]"))
                        for op in ops_data[:5]:
                            top_ops.append({
                                "operation": op.get("name"),
                                "num_calls": op.get("numCalls"),
                                "error_count": op.get("errorCount"),
                                "p50_ms": round(op.get("p50", 0) / 1e6, 2),
                                "p95_ms": round(op.get("p95", 0) / 1e6, 2),
                                "p99_ms": round(op.get("p99", 0) / 1e6, 2)
                            })
                    except Exception:
                        pass

                anomalies.append({
                    "service": name,
                    "error_rate_pct": round(error_rate, 2),
                    "num_errors": num_errors,
                    "num_calls": num_calls,
                    "avg_duration_ms": avg_duration_ms,
                    "p99_latency_ms": p99_ms,
                    "error_anomaly": is_error_anomaly,
                    "latency_anomaly": is_latency_anomaly,
                    "web_url": f"{SIGNOZ_BASE_URL}/services/{name}",
                    "top_operations": top_ops
                })

        return json.dumps({
            "time_range": time_range,
            "filter_service": service_name or "all",
            "anomalies_detected_count": len([a for a in anomalies if a["error_anomaly"] or a["latency_anomaly"]]),
            "services_analyzed": anomalies
        }, indent=2)

    except Exception as e:
        return f"Error analyzing metric anomalies: {str(e)}"


if __name__ == "__main__":
    mcp.run()
