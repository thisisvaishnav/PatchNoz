"""
Incident Orchestrator

Single-alert pipeline: alert -> LLM investigation -> Slack + GitHub actions.
Used by run_patchnoz.py for direct/demo invocations.

For the periodic scan mode (any service, any alert), use ScanOrchestrator
in scan_orchestrator.py instead.
"""

from typing import Optional

from src.action_agent import ActionAgent
from src.llm_agent import LLMInvestigationAgent
from src.models import IncidentAlert, IncidentRun
from src.run_recorder import RunRecorder
from src.self_telemetry import flush_telemetry, start_span


class IncidentOrchestrator:
    """Drives a single alert through investigation and action."""

    def __init__(
        self,
        llm_agent: Optional[LLMInvestigationAgent] = None,
        action_agent: Optional[ActionAgent] = None,
        recorder: Optional[RunRecorder] = None,
    ):
        self.llm_agent = llm_agent or LLMInvestigationAgent()
        self.action_agent = action_agent or ActionAgent()
        self.recorder = recorder or RunRecorder()

    def run(self, alert: IncidentAlert) -> IncidentRun:
        """Investigate a single alert and execute actions. Returns the completed run."""
        run = IncidentRun(alert=alert, status="investigating")
        self.recorder.start(run)

        with start_span(
            "patchnoz.incident.run",
            {
                "incident.id": alert.incident_id,
                "alert.name": alert.alert_name,
                "service.affected": alert.affected_service,
            },
        ) as span:
            try:
                result = self.llm_agent.investigate(alert)
                run.result = result
                run.status = "acting"
                self.recorder.update(run)

                span.set_attribute("llm.confidence_pct", result.confidence_pct)
                span.set_attribute("llm.root_cause_service", result.root_cause_service)

                actions = self.action_agent.execute(result)
                run.actions = actions
                run.status = "completed"

            except Exception as exc:
                run.status = "failed"
                run.error = str(exc)
                span.record_exception(exc)

            finally:
                from datetime import datetime, timezone
                run.end_time = datetime.now(timezone.utc).isoformat()
                self.recorder.finish(run)

        flush_telemetry()
        return run
