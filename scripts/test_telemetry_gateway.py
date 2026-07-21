#!/usr/bin/env python3
"""
Test script for PatchNoz TelemetryGateway, SigNozMCPAdapter, and DiagnosisAgent.

Verifies end-to-end flow:
Alert -> TelemetryGateway (collect_evidence) -> DiagnosisAgent (diagnose) -> RootCauseSummary (JSON handoff)
"""

import sys
import os
import json

# Add src to python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models import IncidentAlert, IncidentEvidence, RootCauseSummary
from src.signoz_mcp_adapter import SigNozMCPAdapter
from src.telemetry_gateway import TelemetryGateway
from src.diagnosis_agent import DiagnosisAgent


def main():
    print("================================================================")
    print("Testing PatchNoz TelemetryGateway & Architecture Refactor")
    print("================================================================")

    # 1. Define IncidentAlert
    alert = IncidentAlert(
        incident_id="demo-checkout-payment-001",
        alert_name="Checkout latency spike",
        severity="critical",
        affected_service="checkout",
        description="P99 latency spike observed on checkout service endpoints"
    )
    print(f"\n[1] Incident Alert Created:\n    ID: {alert.incident_id}\n    Service: {alert.affected_service}\n    Severity: {alert.severity}")

    # 2. Instantiate TelemetryGateway
    gateway = TelemetryGateway()

    print("\n[2] TelemetryGateway collecting evidence via SigNozMCPAdapter...")
    evidence = gateway.collect_evidence(alert)

    print(f"    Collected {len(evidence.evidence_items)} evidence summary items:")
    for item in evidence.evidence_items:
        print(f"     - [{item.source}] {item.summary}")

    print(f"    Traces fetched: {len(evidence.traces_summary)}")
    print(f"    Logs fetched: {len(evidence.logs_summary)}")
    print(f"    Anomalous services: {evidence.suspected_services}")

    # 3. Diagnose root cause using DiagnosisAgent
    print("\n[3] Diagnosing incident root cause using DiagnosisAgent...")
    agent = DiagnosisAgent()
    root_cause = agent.diagnose(alert, evidence)

    # 4. Print minimum useful JSON handoff
    print("\n[4] Standard Minimum Useful JSON Handoff Output:")
    print("----------------------------------------------------------------")
    json_output = root_cause.to_json(indent=2)
    print(json_output)
    print("----------------------------------------------------------------")

    # Validate JSON shape
    handoff = json.loads(json_output)
    assert handoff["incident_id"] == "demo-checkout-payment-001"
    assert handoff["affected_service"] == "checkout"
    assert "suspected_root_cause_service" in handoff
    assert "suspected_root_cause" in handoff
    assert "evidence" in handoff
    assert "recommended_fix" in handoff

    print("\n================================================================")
    print("SUCCESS: TelemetryGateway & JSON Handoff architecture verified!")
    print("================================================================")


if __name__ == "__main__":
    main()
