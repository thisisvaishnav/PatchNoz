"""
PatchNoz CLI Adapter

Entry point to execute PatchNoz incident diagnosis runs.
Example:
    python src/run_patchnoz.py --scenario checkout-payment-latency
"""

import argparse
import sys
import os

# Add repo root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.models import IncidentAlert
from src.orchestrator import IncidentOrchestrator


SCENARIO_CONFIGS = {
    "checkout-payment-latency": {
        "incident_id": "demo-checkout-payment",
        "alert_name": "CheckoutService High P99 Latency & Payment Errors",
        "severity": "critical",
        "affected_service": "checkout",
        "description": "High latency and elevated error rates observed on checkout service during peak payment traffic.",
        "default_output_dir": "runs/demo-checkout-payment"
    }
}


def main():
    parser = argparse.ArgumentParser(description="PatchNoz - AI-powered SRE Teammate")
    parser.add_argument(
        "--scenario",
        type=str,
        default="checkout-payment-latency",
        help="Predefined demo scenario name (e.g. checkout-payment-latency)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for run artifacts (default: runs/demo-<scenario>)"
    )

    args = parser.parse_args()
    scenario_key = args.scenario.lower()

    if scenario_key in SCENARIO_CONFIGS:
        cfg = SCENARIO_CONFIGS[scenario_key]
    else:
        # Generic fallback for unlisted scenarios
        clean_name = scenario_key.replace("_", "-")
        service_name = clean_name.split("-")[0] if "-" in clean_name else clean_name
        cfg = {
            "incident_id": f"demo-{clean_name}",
            "alert_name": f"{service_name.capitalize()} High Latency / Anomaly",
            "severity": "critical",
            "affected_service": service_name,
            "description": f"Automated scenario alert for {scenario_key}.",
            "default_output_dir": f"runs/demo-{clean_name}"
        }

    output_dir = args.output_dir or cfg["default_output_dir"]

    alert = IncidentAlert(
        incident_id=cfg["incident_id"],
        alert_name=cfg["alert_name"],
        severity=cfg["severity"],
        affected_service=cfg["affected_service"],
        description=cfg["description"]
    )

    print("==================================================")
    print("🚀 PatchNoz Incident Diagnosis Run")
    print(f"Scenario: {args.scenario}")
    print(f"Incident ID: {alert.incident_id}")
    print(f"Service: {alert.affected_service}")
    print(f"Artifacts Destination: {output_dir}")
    print("==================================================")

    orchestrator = IncidentOrchestrator()
    run_result = orchestrator.run(alert, output_dir=output_dir)

    print("\n✅ Run Completed Successfully!")
    print(f"Status: {run_result.status}")
    if run_result.root_cause:
        print(f"Suspected Root Cause Service: {run_result.root_cause.suspected_root_cause_service}")
        print(f"Root Cause: {run_result.root_cause.suspected_root_cause}")
        print(f"Recommended Fix: {run_result.root_cause.recommended_fix}")
    print(f"\nArtifacts saved to: {output_dir}/")
    print("  - alert.json")
    print("  - evidence.json")
    print("  - root_cause.json")
    print("  - progress.md")
    print("==================================================")


if __name__ == "__main__":
    main()
