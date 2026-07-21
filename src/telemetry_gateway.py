"""
Telemetry Gateway

A PatchNoz-shaped view over SigNoz telemetry. Wraps SigNozMCPAdapter and
normalizes its raw MCP tool responses into EvidenceItem objects, so the
rest of PatchNoz never has to know SigNoz's wire format.

Each underlying SigNoz MCP call is isolated: if one tool call fails
(timeout, auth issue, unknown service, ...) that failure becomes a single
"error" EvidenceItem instead of aborting the whole evidence collection.
"""

from typing import Any, Dict, List, Optional

from src.models import EvidenceItem, IncidentAlert, IncidentEvidence
from src.self_telemetry import start_span
from src.signoz_mcp_adapter import SIGNOZ_BASE_URL, SigNozMCPAdapter, default_adapter


class TelemetryGateway:
    """Collects and normalizes SigNoz evidence relevant to an incident alert."""

    def __init__(self, adapter: Optional[SigNozMCPAdapter] = None, base_url: str = SIGNOZ_BASE_URL):
        self.adapter = adapter or default_adapter
        self.base_url = base_url

    def collect_evidence(self, alert: IncidentAlert) -> IncidentEvidence:
        """
        Collects service health, trace, and log evidence for an alert.

        For the checkout-payment-latency demo scenario this means:
        signoz_list_services, signoz_search_traces for "checkout",
        signoz_search_traces for "payment", and signoz_search_logs for
        "payment" - driven generically here by alert.affected_service and
        alert.suspected_area.
        """
        evidence = IncidentEvidence(incident_id=alert.incident_id)

        primary_service = alert.affected_service
        secondary_service = alert.suspected_area or primary_service

        with start_span(
            "patchnoz.telemetry.collect_evidence",
            {"incident.id": alert.incident_id, "service.affected": primary_service},
        ):
            self._collect_service_health(evidence, primary_service)
            self._collect_traces(evidence, primary_service)

            if secondary_service and secondary_service != primary_service:
                self._collect_traces(evidence, secondary_service)
                self._collect_logs(evidence, secondary_service)
            else:
                self._collect_logs(evidence, primary_service)

        return evidence

    # --- Individual collectors, each resilient to its own failure ---

    def _collect_service_health(self, evidence: IncidentEvidence, service: str) -> None:
        try:
            result = self.adapter.list_services()
            services = self._extract_rows(result)
            match = next(
                (s for s in services if str(s.get("serviceName", "")).lower() == service.lower()),
                None,
            )
            if match:
                p99_ms = round(match.get("p99", 0) / 1e6, 2)
                error_rate = round(match.get("errorRate", 0.0), 2)
                summary = f"{service} metrics: p99 latency {p99_ms}ms, error rate {error_rate}%"
            else:
                summary = f"No service health data found for '{service}' ({len(services)} services known to SigNoz)."
            evidence.add(EvidenceItem(
                source="metrics",
                service=service,
                summary=summary,
                raw=match or {"known_services": [s.get("serviceName") for s in services]},
                url=self._service_link(service),
            ))
        except Exception as e:
            evidence.add(EvidenceItem(
                source="error",
                service=service,
                summary=f"Failed to fetch service metrics for '{service}': {e}",
            ))

    def _collect_traces(self, evidence: IncidentEvidence, service: str) -> None:
        try:
            result = self.adapter.search_traces(service, limit=5)
            rows = self._extract_rows(result)
            trace_url = None
            if rows:
                slowest = max(rows, key=lambda r: r.get("data", {}).get("duration_nano", 0))
                data = slowest.get("data", {})
                trace_id = data.get("trace_id")
                op_name = data.get("name", "")
                duration_ms = round(data.get("duration_nano", 0) / 1e6, 2)
                summary = f"Slowest recent trace on '{service}': {op_name} ({duration_ms}ms)"
                trace_url = self._trace_link(trace_id) if trace_id else None
            else:
                summary = f"No recent traces found for '{service}'."
            evidence.add(EvidenceItem(
                source="traces",
                service=service,
                summary=summary,
                raw=rows,
                url=trace_url or self._service_link(service),
            ))
        except Exception as e:
            evidence.add(EvidenceItem(
                source="error",
                service=service,
                summary=f"Failed to fetch traces for '{service}': {e}",
            ))

    def _collect_logs(self, evidence: IncidentEvidence, service: str) -> None:
        try:
            result = self.adapter.search_logs(service, limit=10)
            rows = self._extract_rows(result)
            if rows:
                body = str(rows[0].get("data", {}).get("body", ""))[:120]
                summary = f"{len(rows)} recent log entries for '{service}'; latest: {body}"
            else:
                summary = f"No recent logs found for '{service}'."
            evidence.add(EvidenceItem(
                source="logs",
                service=service,
                summary=summary,
                raw=rows,
                url=self._service_link(service),
            ))
        except Exception as e:
            evidence.add(EvidenceItem(
                source="error",
                service=service,
                summary=f"Failed to fetch logs for '{service}': {e}",
            ))

    # --- Helpers ---

    @staticmethod
    def _extract_rows(result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Best-effort extraction of row/list data from SigNoz's nested MCP result shapes."""
        if not isinstance(result, dict):
            return []
        if isinstance(result.get("data"), list):
            return result["data"]
        results = result.get("data", {}).get("data", {}).get("results", [])
        if results and results[0].get("rows"):
            return results[0]["rows"]
        return []

    def _service_link(self, service: str) -> str:
        return f"{self.base_url}/services/{service}"

    def _trace_link(self, trace_id: str) -> str:
        return f"{self.base_url}/trace/{trace_id}"
