"""
PatchNoz CLI

Entry point for running a PatchNoz incident diagnosis pass end-to-end:

    python src/run_patchnoz.py --scenario checkout-payment-latency
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.models import IncidentAlert
from src.orchestrator import IncidentOrchestrator
from src.self_telemetry import configure_tracing

SCENARIOS = {
    "checkout-payment-latency": {
        "incident_id": "demo-checkout-payment",
        "alert_name": "Checkout latency spike",
        "severity": "critical",
        "affected_service": "checkout",
        "condition": "p99 latency > 1s",
        "time_range": "15m",
        "suspected_area": "payment",
    },
}


def build_alert(scenario: str) -> IncidentAlert:
    if scenario not in SCENARIOS:
        available = ", ".join(SCENARIOS)
        raise SystemExit(f"Unknown scenario '{scenario}'. Available scenarios: {available}")
    return IncidentAlert(**SCENARIOS[scenario])


def main() -> None:
    parser = argparse.ArgumentParser(description="PatchNoz - AutoSRE-lite incident pipeline on SigNoz")
    parser.add_argument(
        "--scenario",
        default="checkout-payment-latency",
        help="Demo scenario to simulate (default: checkout-payment-latency)",
    )
    args = parser.parse_args()

    tracer = configure_tracing()
    alert = build_alert(args.scenario)

    print("=" * 60)
    print("PatchNoz Incident Run")
    print(f"Scenario:         {args.scenario}")
    print(f"Incident ID:      {alert.incident_id}")
    print(f"Affected service: {alert.affected_service}")
    print("=" * 60)

    with tracer.start_as_current_span("patchnoz.cli.run") as span:
        span.set_attribute("patchnoz.scenario", args.scenario)
        span.set_attribute("incident.id", alert.incident_id)
        orchestrator = IncidentOrchestrator()
        run_result = orchestrator.run(alert)

    print()
    print(f"Status: {run_result.status}")
    if run_result.error:
        print(f"Error: {run_result.error}")

    if run_result.root_cause:
        rc = run_result.root_cause
        print()
        print("Root cause summary")
        print("-" * 60)
        print(f"Suspected root cause service : {rc.suspected_root_cause_service}")
        print(f"Suspected root cause         : {rc.suspected_root_cause}")
        print(f"Recommended fix              : {rc.recommended_fix}")
        print(f"Confidence                   : {rc.confidence:.0%}")
        if rc.sig_noz_links:
            print("SigNoz links:")
            for link in rc.sig_noz_links:
                print(f"  - {link}")

    if run_result.actions:
        print()
        print("Actions")
        print("-" * 60)
        for action in run_result.actions:
            url_suffix = f" -> {action.url}" if action.url else ""
            print(f"  [{action.status:>8}] {action.name}{url_suffix}")

    run_dir = os.path.join("runs", alert.incident_id)
    print()
    print(f"Artifacts saved to: {run_dir}/")
    for filename in ("alert.json", "evidence.json", "root_cause.json", "actions.json", "progress.md"):
        print(f"  - {filename}")
    print("=" * 60)


if __name__ == "__main__":
    main()
