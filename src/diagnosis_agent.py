"""
Diagnosis Agent

Rule-based synthesis of collected SigNoz evidence into a RootCauseSummary.
Deterministic on purpose (no LLM call yet) - tuned for the
checkout-payment-latency demo scenario, but degrades gracefully for other
services.
"""

from src.models import IncidentAlert, IncidentEvidence, RootCauseSummary
from src.self_telemetry import start_span


class DiagnosisAgent:
    """Synthesizes IncidentEvidence into a RootCauseSummary."""

    def diagnose(self, alert: IncidentAlert, evidence: IncidentEvidence) -> RootCauseSummary:
        with start_span(
            "patchnoz.diagnosis.summarize",
            {"incident.id": alert.incident_id, "service.affected": alert.affected_service},
        ):
            payment_evidence = self._find_payment_evidence(evidence)

            if payment_evidence or self._mentions_payment(alert):
                root_cause_service = "payment"
                suspected_root_cause = (
                    "Checkout latency appears to be dominated by payment charge spans. "
                    "The likely root cause is slow or failing payment processing during checkout."
                )
                recommended_fix = (
                    "Add timeout, retry, and circuit-breaker handling around the payment charge call. "
                    "Add metrics for payment dependency latency and error rate."
                )
                confidence = 0.85 if payment_evidence else 0.7
            else:
                root_cause_service = alert.affected_service
                suspected_root_cause = (
                    f"Evidence points to degraded performance directly on '{alert.affected_service}'; "
                    "no clear downstream dependency stood out in the collected traces/logs."
                )
                recommended_fix = (
                    f"Inspect resource limits, recent deploys, and downstream dependencies for "
                    f"'{alert.affected_service}'."
                )
                confidence = 0.5

            links = [item.url for item in evidence.items if item.url]
            deduped_links = list(dict.fromkeys(links))

            return RootCauseSummary(
                incident_id=alert.incident_id,
                severity=alert.severity,
                affected_service=alert.affected_service,
                suspected_root_cause_service=root_cause_service,
                suspected_root_cause=suspected_root_cause,
                evidence=list(evidence.items),
                recommended_fix=recommended_fix,
                confidence=confidence,
                sig_noz_links=deduped_links,
            )

    @staticmethod
    def _find_payment_evidence(evidence: IncidentEvidence):
        for item in evidence.items:
            haystack = f"{item.service} {item.summary}".lower()
            if "payment" in haystack or "charge" in haystack:
                return item
        return None

    @staticmethod
    def _mentions_payment(alert: IncidentAlert) -> bool:
        return "payment" in (alert.suspected_area or "").lower()
