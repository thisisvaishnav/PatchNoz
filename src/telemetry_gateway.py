"""
Telemetry Gateway

Provides a clean, domain-specific telemetry interface for PatchNoz.
Decouples diagnosis and orchestration modules from native SigNoz MCP tool names.
"""

from typing import List, Dict, Any, Optional
from src.models import IncidentAlert, IncidentEvidence, EvidenceItem
from src.signoz_mcp_adapter import SigNozMCPAdapter, default_adapter


class TelemetryGateway:
    """
    Gateway exposing high-level telemetry operations for PatchNoz agents.
    Uses SigNozMCPAdapter under the hood.
    """

    def __init__(self, adapter: Optional[SigNozMCPAdapter] = None):
        self.adapter = adapter or default_adapter

    def collect_evidence(self, alert: IncidentAlert) -> IncidentEvidence:
        """
        Collects metrics, trace, and log evidence relevant to an incident alert.

        Args:
            alert: IncidentAlert domain model containing affected service and alert details.

        Returns:
            IncidentEvidence containing summarized evidence items and detailed raw collections.
        """
        service_name = alert.affected_service
        evidence = IncidentEvidence(
            incident_id=alert.incident_id,
            affected_service=service_name
        )

        # 1. Collect metrics and health anomalies across services
        all_services = self.adapter.list_services()
        anomalies = []
        affected_svc_data = None
        suspected_services = [service_name]

        for svc in all_services:
            svc_name = svc.get("serviceName", "")
            error_rate = svc.get("errorRate", 0.0)
            p99_ms = round(svc.get("p99", 0) / 1e6, 2)
            num_errors = svc.get("numErrors", 0)
            num_calls = svc.get("numCalls", 0)

            is_error_anomaly = error_rate > 1.0  # >1% error rate
            is_latency_anomaly = p99_ms > 1000.0  # >1s p99 latency

            if svc_name.lower() == service_name.lower():
                affected_svc_data = svc

            if is_error_anomaly or is_latency_anomaly or svc_name.lower() == service_name.lower():
                top_ops = self.adapter.get_top_operations(svc_name)
                anomalies.append({
                    "service": svc_name,
                    "error_rate_pct": round(error_rate, 2),
                    "num_errors": num_errors,
                    "num_calls": num_calls,
                    "p99_latency_ms": p99_ms,
                    "error_anomaly": is_error_anomaly,
                    "latency_anomaly": is_latency_anomaly,
                    "top_operations": top_ops
                })
                if svc_name not in suspected_services:
                    suspected_services.append(svc_name)

        evidence.metrics_anomalies = anomalies
        evidence.suspected_services = suspected_services

        # Add metric evidence item
        if affected_svc_data:
            p99_ms = round(affected_svc_data.get("p99", 0) / 1e6, 2)
            err_rate = round(affected_svc_data.get("errorRate", 0.0), 2)
            summary_msg = f"{service_name} metrics: p99 latency is {p99_ms}ms, error rate is {err_rate}%"
            evidence.add_evidence("metrics", summary_msg, details=affected_svc_data)
        else:
            evidence.add_evidence("metrics", f"{service_name} p99 latency is above threshold")

        # 2. Collect traces for the affected service (and any anomalous downstream services)
        traces = self.adapter.search_traces(service_name, limit=10)
        evidence.traces_summary = traces

        slow_spans = []
        error_spans = []
        for tr in traces:
            if tr.get("has_error"):
                error_spans.append(tr)
            if tr.get("duration_ms", 0) > 500:
                slow_spans.append(tr)

        if slow_spans:
            op_names = list(set(tr.get("operation", "") for tr in slow_spans if tr.get("operation")))
            op_str = ", ".join(op_names[:3])
            summary_msg = f"slow traces include dominant operations: {op_str}" if op_str else "slow traces detected in service"
            evidence.add_evidence("traces", summary_msg, details={"slow_count": len(slow_spans)})
        elif error_spans:
            evidence.add_evidence("traces", f"error spans detected in {service_name} traces", details={"error_count": len(error_spans)})
        else:
            evidence.add_evidence("traces", f"analyzed {len(traces)} recent traces for service {service_name}")

        # 3. Collect logs (error/warn logs or query logs)
        error_logs = self.adapter.search_logs(service_name, severity="ERROR", limit=10)
        if not error_logs:
            # Fall back to general logs for service
            error_logs = self.adapter.search_logs(service_name, limit=10)
        
        evidence.logs_summary = error_logs
        if error_logs:
            body_snippet = error_logs[0].get("body", "")
            if len(body_snippet) > 100:
                body_snippet = body_snippet[:100] + "..."
            summary_msg = f"log entries found: {body_snippet}" if body_snippet else f"found {len(error_logs)} recent log entries for {service_name}"
            evidence.add_evidence("logs", summary_msg, details={"log_count": len(error_logs)})

        return evidence

    def get_all_services_health(self) -> List[Dict[str, Any]]:
        """Returns health summary across all monitored services."""
        return self.adapter.list_services()

    def get_recent_traces(self, service_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Returns recent trace data for a service."""
        return self.adapter.search_traces(service_name, limit=limit)

    def get_recent_logs(self, service_name: str, limit: int = 20, query: str = "", severity: str = "") -> List[Dict[str, Any]]:
        """Returns recent log entries for a service."""
        return self.adapter.search_logs(service_name, limit=limit, query=query, severity=severity)
