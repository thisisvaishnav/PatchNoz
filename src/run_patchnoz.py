"""
PatchNoz CLI (demo / single-alert mode)

Runs a single alert through the full LLM investigation pipeline:

    python src/run_patchnoz.py --scenario checkout-payment-latency

For the periodic scan mode that automatically discovers firing alerts
across all SigNoz services, use run_scanner.py instead.
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
        raise SystemExit(f"Unknown scenario '{scenario}'. Available: {available}")
    return IncidentAlert(**SCENARIOS[scenario])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PatchNoz - single alert LLM investigation (demo mode). "
                    "For scan mode use run_scanner.py."
    )
    parser.add_argument(
        "--scenario",
        default="checkout-payment-latency",
        help="Demo scenario (default: checkout-payment-latency)",
    )
    args = parser.parse_args()

    tracer = configure_tracing()
    alert = build_alert(args.scenario)

    print("=" * 60)
    print("PatchNoz — LLM Investigation (demo mode)")
    print(f"Scenario:         {args.scenario}")
    print(f"Incident ID:      {alert.incident_id}")
    print(f"Affected service: {alert.affected_service}")
    print("=" * 60)

    with tracer.start_as_current_span("patchnoz.cli.run") as span:
        span.set_attribute("patchnoz.scenario", args.scenario)
        span.set_attribute("incident.id", alert.incident_id)
        orchestrator = IncidentOrchestrator()
        run = orchestrator.run(alert)

    print()
    print(f"Status: {run.status}")
    if run.error:
        print(f"Error:  {run.error}")

    if run.result:
        r = run.result
        print()
        print("Investigation result")
        print("-" * 60)
        print(f"Root cause service : {r.root_cause_service}")
        print(f"Error observed     : {r.error_message or '(none found)'}")
        print(f"Confidence         : {r.confidence_pct}%")
        print(f"Reasoning          : {r.confidence_reasoning}")
        print(f"Tool calls used    : {r.tool_calls_made}")
        if r.recommended_fix_steps:
            print("Fix steps:")
            for i, step in enumerate(r.recommended_fix_steps, 1):
                print(f"  {i}. {step}")
        if r.signoz_links:
            print("SigNoz links:")
            for link in r.signoz_links:
                print(f"  - {link}")

    if run.actions:
        print()
        print("Actions")
        print("-" * 60)
        for action in run.actions:
            url_suffix = f" -> {action.url}" if action.url else ""
            print(f"  [{action.status:>8}] {action.name}{url_suffix}")

    run_dir = os.path.join("runs", alert.incident_id)
    print()
    print(f"Artifacts saved to: {run_dir}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
