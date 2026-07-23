"""
PatchNoz Scanner -- CLI entry point for the Scan cycle mode.

Usage:
    python src/run_scanner.py              # run once, then exit
    python src/run_scanner.py --loop       # run forever (every 15 min by default)
    python src/run_scanner.py --loop --interval 300   # every 5 minutes

Environment variables (set in .env or shell):
    GEMINI_API_KEY              Required. Get free key at https://aistudio.google.com
    SIGNOZ_MCP_URL              Default: http://localhost:8000/mcp
    SIGNOZ_BASE_URL             Default: http://localhost:8080
    SIGNOZ_API_KEY              SigNoz auth (preferred)
    SLACK_WEBHOOK_URL           Optional. Enables real Slack posts.
    GITHUB_TOKEN / GITHUB_OWNER / GITHUB_REPO  Optional. Enables real GitHub issues.
    PATCHNOZ_SCAN_INTERVAL_SECS Default: 900 (15 min)
    PATCHNOZ_MAX_TOOL_CALLS     Default: 12
    GEMINI_MODEL                Default: gemini-2.5-flash
"""

import argparse
import sys

# Ensure src/ is on the path when running as `python src/run_scanner.py`
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.env import load_env
from src.scan_orchestrator import ScanOrchestrator

load_env()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PatchNoz: autonomous SRE agent that investigates SigNoz alerts."
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run forever, scanning on a fixed interval (default: once then exit).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Scan interval in seconds when --loop is set (overrides PATCHNOZ_SCAN_INTERVAL_SECS).",
    )
    args = parser.parse_args()

    orchestrator = ScanOrchestrator()

    if args.loop:
        from src.scan_orchestrator import SCAN_INTERVAL_SECS
        interval = args.interval or SCAN_INTERVAL_SECS
        orchestrator.run_forever(interval_secs=interval)
    else:
        runs = orchestrator.run_once()
        if not runs:
            print("No new alerts to investigate. All firing alerts already have open GitHub issues, or none are firing.")
        else:
            for run in runs:
                status = "✅" if run.status == "completed" else "❌"
                print(f"{status} {run.alert.incident_id}: {run.status}")
                if run.result:
                    print(f"   Root cause: {run.result.root_cause_service} ({run.result.confidence_pct}% confidence)")
                for action in run.actions:
                    url_part = f" → {action.url}" if action.url else ""
                    print(f"   {action.name}: {action.status}{url_part}")


if __name__ == "__main__":
    main()
