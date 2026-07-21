"""
SigNoz Custom MCP Server (DEMOTED / NOT PART OF THE CURRENT PIPELINE)

PatchNoz's core flow does not run its own MCP server - it consumes
SigNoz's prebuilt MCP server directly via SigNozMCPAdapter /
TelemetryGateway (see src/telemetry_gateway.py). This module predates
that decision and is kept only for reference; it is not imported by
src/orchestrator.py or src/run_patchnoz.py, and its calls into
TelemetryGateway are stale after the TelemetryGateway.collect_evidence
refactor. Do not build this out further; the constraint for PatchNoz is
to consume SigNoz's MCP server, not to ship a competing one.
"""

import json
from typing import Optional
from mcp.server.fastmcp import FastMCP
from src.telemetry_gateway import TelemetryGateway

# Initialize FastMCP Server
mcp = FastMCP(
    "SigNoz Custom MCP Server",
    instructions="MCP Server providing tools to query traces, logs, and metric anomalies via TelemetryGateway."
)

gateway = TelemetryGateway()


@mcp.tool()
def get_recent_traces(service_name: str, time_range: str = "15m", limit: int = 10) -> str:
    """Fetch recent traces for a service."""
    traces = gateway.get_recent_traces(service_name, limit=limit)
    if not traces:
        return f"No recent traces found for service '{service_name}' in the last {time_range}."
    return json.dumps({
        "service": service_name,
        "time_range": time_range,
        "total_fetched": len(traces),
        "traces": traces
    }, indent=2)


@mcp.tool()
def get_recent_logs(service_name: str, time_range: str = "15m", query: str = "", severity: str = "", limit: int = 20) -> str:
    """Fetch recent logs for a service."""
    logs = gateway.get_recent_logs(service_name, limit=limit, query=query, severity=severity)
    if not logs:
        return f"No recent logs found for service '{service_name}' (query: '{query}', severity: '{severity}') in the last {time_range}."
    return json.dumps({
        "service": service_name,
        "time_range": time_range,
        "total_fetched": len(logs),
        "logs": logs
    }, indent=2)


@mcp.tool()
def get_metric_anomalies(service_name: str = "", metric_name: str = "", time_range: str = "1h") -> str:
    """Detect metric anomalies across services."""
    services = gateway.get_all_services_health()
    anomalies = []
    for svc in services:
        name = svc.get("serviceName", "")
        if service_name and name.lower() != service_name.lower():
            continue

        error_rate = svc.get("errorRate", 0.0)
        p99_ms = round(svc.get("p99", 0) / 1e6, 2)

        is_error_anomaly = error_rate > 1.0
        is_latency_anomaly = p99_ms > 1000.0

        if is_error_anomaly or is_latency_anomaly or service_name:
            top_ops = gateway.adapter.get_top_operations(name)
            anomalies.append({
                "service": name,
                "error_rate_pct": round(error_rate, 2),
                "num_errors": svc.get("numErrors", 0),
                "num_calls": svc.get("numCalls", 0),
                "p99_latency_ms": p99_ms,
                "error_anomaly": is_error_anomaly,
                "latency_anomaly": is_latency_anomaly,
                "top_operations": top_ops
            })

    return json.dumps({
        "time_range": time_range,
        "filter_service": service_name or "all",
        "anomalies_detected_count": len([a for a in anomalies if a["error_anomaly"] or a["latency_anomaly"]]),
        "services_analyzed": anomalies
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
