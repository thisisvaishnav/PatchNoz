"""
Scan Orchestrator

Implements the periodic Scan cycle:
  1. Call signoz_list_alerts to get all currently firing alerts.
  2. For each alert, check GitHub for an existing open issue (deduplication).
  3. For each new alert (no open issue), run a full LLM Investigation.
  4. Post the InvestigationResult to Slack and open a GitHub issue.
  5. Record the run to runs/<incident_id>/.

Runs as a blocking loop (call run_forever()) or as a single sweep
(call run_once()). The loop interval is configurable via PATCHNOZ_SCAN_INTERVAL_SECS.
"""

import os
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.action_agent import ActionAgent
from src.adapters.github import find_open_issue
from src.env import load_env
from src.llm_agent import LLMInvestigationAgent
from src.models import IncidentAlert, IncidentRun, InvestigationResult
from src.run_recorder import RunRecorder
from src.self_telemetry import start_span
from src.signoz_mcp_adapter import default_adapter

load_env()

SCAN_INTERVAL_SECS = int(os.getenv("PATCHNOZ_SCAN_INTERVAL_SECS", "900"))  # 15 min default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_firing_alerts(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Backward compatibility helper delegating to SigNozMCPAdapter."""
    from src.signoz_mcp_adapter import SigNozMCPAdapter
    return SigNozMCPAdapter._parse_firing_alerts(raw)


class ScanOrchestrator:
    """
    Runs periodic Scan cycles against SigNoz and investigates firing alerts.
    """

    def __init__(
        self,
        llm_agent: Optional[LLMInvestigationAgent] = None,
        action_agent: Optional[ActionAgent] = None,
        recorder: Optional[RunRecorder] = None,
    ):
        self.llm_agent = llm_agent or LLMInvestigationAgent()
        self.action_agent = action_agent or ActionAgent()
        self.recorder = recorder or RunRecorder()

    def run_forever(self, interval_secs: int = SCAN_INTERVAL_SECS) -> None:
        """Block forever, running a scan sweep every interval_secs seconds."""
        print(f"[ScanOrchestrator] Starting scan loop (interval: {interval_secs}s)")
        while True:
            try:
                self.run_once()
            except KeyboardInterrupt:
                print("[ScanOrchestrator] Stopped by user.")
                break
            except Exception:
                print("[ScanOrchestrator] Unhandled error in scan cycle:")
                traceback.print_exc()
            print(f"[ScanOrchestrator] Sleeping {interval_secs}s until next scan...")
            time.sleep(interval_secs)

    def run_once(self) -> List[IncidentRun]:
        """
        Run a single Scan cycle. Returns one IncidentRun per investigated alert.
        Alerts that already have an open GitHub issue are skipped.
        """
        print(f"[ScanOrchestrator] Scan started at {_now_iso()}")
        runs: List[IncidentRun] = []

        with start_span("patchnoz.scan.cycle"):
            firing = self._fetch_firing_alerts()
            print(f"[ScanOrchestrator] Found {len(firing)} firing alert(s).")

            for raw_alert in firing:
                try:
                    alert = IncidentAlert.from_signoz_alert(raw_alert)
                except Exception as exc:
                    print(f"[ScanOrchestrator] Could not parse alert {raw_alert}: {exc}")
                    continue

                run = self._handle_alert(alert)
                if run:
                    runs.append(run)

        print(f"[ScanOrchestrator] Scan complete. Investigated {len(runs)} alert(s).")
        return runs

    def _fetch_firing_alerts(self) -> List[Dict[str, Any]]:
        try:
            return default_adapter.list_firing_alerts()
        except Exception as exc:
            print(f"[ScanOrchestrator] Failed to fetch alerts: {exc}")
            return []

    def _handle_alert(self, alert: IncidentAlert) -> Optional[IncidentRun]:
        """
        Investigate one alert if it doesn't already have an open GitHub issue.
        Returns an IncidentRun on success, None if skipped.
        """
        print(f"[ScanOrchestrator] Alert: {alert.alert_name} | service: {alert.affected_service}")

        # --- Deduplication: check GitHub before investigating ---
        # Build a minimal stub result just to compute the label for the search
        stub = InvestigationResult(
            alert_id=alert.incident_id,
            alert_name=alert.alert_name,
            severity=alert.severity,
            affected_service=alert.affected_service,
            root_cause_service=alert.affected_service,
            error_message="",
            affected_user_pattern="",
            affected_service_p99_ms=0.0,
            root_cause_error_rate_pct=0.0,
            confidence_pct=0,
            confidence_reasoning="",
            recommended_fix_steps=[],
            slack_one_liner="",
            github_body="",
        )
        existing_url = find_open_issue(stub)
        if existing_url:
            print(f"[ScanOrchestrator] Skipping {alert.alert_name} -- open issue exists: {existing_url}")
            return None

        # --- Run investigation ---
        run = IncidentRun(alert=alert)
        self.recorder.start(run)

        with start_span(
            "patchnoz.incident.run",
            {"incident.id": alert.incident_id, "service.affected": alert.affected_service},
        ):
            try:
                run.status = "investigating"
                self.recorder.update(run)

                result: InvestigationResult = self.llm_agent.investigate(alert)
                run.result = result
                run.status = "acting"
                self.recorder.update(run)

                print(
                    f"[ScanOrchestrator] Investigation complete: "
                    f"root_cause={result.root_cause_service} "
                    f"confidence={result.confidence_pct}%"
                )

                actions = self.action_agent.execute(result)
                run.actions = actions
                run.status = "completed"

            except Exception as exc:
                run.status = "failed"
                run.error = str(exc)
                traceback.print_exc()

            finally:
                run.end_time = _now_iso()
                self.recorder.finish(run)

        return run
