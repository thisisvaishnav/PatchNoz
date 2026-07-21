"""
Diagnosis Agent

Analyzes IncidentEvidence collected by TelemetryGateway and produces a RootCauseSummary.
Completely decoupled from native SigNoz MCP tool names.
"""

from typing import Optional
from src.models import IncidentAlert, IncidentEvidence, RootCauseSummary


class DiagnosisAgent:
    """
    Agent responsible for analyzing evidence and synthesizing root-cause summaries.
    """

    def diagnose(self, alert: IncidentAlert, evidence: IncidentEvidence) -> RootCauseSummary:
        """
        Diagnoses the root cause based on alert metadata and collected evidence.

        Args:
            alert: IncidentAlert domain object
            evidence: IncidentEvidence domain object collected by TelemetryGateway

        Returns:
            RootCauseSummary matching the PatchNoz standard JSON handoff shape.
        """
        affected_service = alert.affected_service
        suspected_root_cause_service = affected_service
        suspected_root_cause = f"Increased latency or errors detected on {affected_service}."
        recommended_fix = f"Inspect downstream dependencies and resource limits for {affected_service}."

        # Analyze metric anomalies to find root cause service
        for anomaly in evidence.metrics_anomalies:
            svc = anomaly.get("service", "")
            err_rate = anomaly.get("error_rate_pct", 0)
            p99 = anomaly.get("p99_latency_ms", 0)

            if err_rate > 5.0 or p99 > 2000.0:
                suspected_root_cause_service = svc
                top_ops = anomaly.get("top_operations", [])
                op_name = top_ops[0].get("operation") if top_ops else f"{svc} endpoints"
                suspected_root_cause = f"{affected_service} performance degraded due to {svc} ({op_name}) experiencing high latency/errors (p99: {p99}ms, error_rate: {err_rate}%)."
                recommended_fix = f"Add timeout, retry, and circuit-breaker handling around the {svc} service calls."
                break

        # Check trace evidence if available
        if not suspected_root_cause_service or suspected_root_cause_service == affected_service:
            for tr in evidence.traces_summary:
                if "payment" in tr.get("operation", "").lower() or tr.get("duration_ms", 0) > 1000:
                    suspected_root_cause_service = "payment"
                    suspected_root_cause = f"Checkout latency is dominated by {tr.get('operation')} spans."
                    recommended_fix = "Add timeout and retry/circuit-breaker handling around the payment charge call."
                    break

        return RootCauseSummary(
            incident_id=alert.incident_id,
            alert_name=alert.alert_name,
            severity=alert.severity,
            affected_service=affected_service,
            suspected_root_cause_service=suspected_root_cause_service,
            suspected_root_cause=suspected_root_cause,
            evidence=evidence.get_summary_list(),
            recommended_fix=recommended_fix
        )
