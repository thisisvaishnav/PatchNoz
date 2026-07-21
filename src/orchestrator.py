"""
Incident Orchestrator

Owns the end-to-end incident pipeline and its ordering/failure handling:

    alert -> save alert
          -> collect evidence (TelemetryGateway) -> save evidence
          -> diagnose (DiagnosisAgent) -> save root cause
          -> act (ActionAgent) -> save actions
          -> save progress
          -> self-telemetry flushed to SigNoz
"""

from datetime import datetime, timezone
from typing import List, Optional

from src.action_agent import ActionAgent
from src.diagnosis_agent import DiagnosisAgent
from src.models import IncidentAlert, IncidentRun
from src.run_recorder import RunRecorder
from src.self_telemetry import flush_telemetry, start_span
from src.telemetry_gateway import TelemetryGateway


class IncidentOrchestrator:
    """Drives a single incident from alert to recorded, actioned diagnosis."""

    def __init__(
        self,
        gateway: Optional[TelemetryGateway] = None,
        diagnosis_agent: Optional[DiagnosisAgent] = None,
        action_agent: Optional[ActionAgent] = None,
        recorder: Optional[RunRecorder] = None,
    ):
        self.gateway = gateway or TelemetryGateway()
        self.diagnosis_agent = diagnosis_agent or DiagnosisAgent()
        self.action_agent = action_agent or ActionAgent()
        self.recorder = recorder or RunRecorder()

    def run(self, alert: IncidentAlert) -> IncidentRun:
        """Runs the full diagnose-and-act pipeline for a single alert."""
        incident_run = IncidentRun(alert=alert, status="diagnosing")
        progress: List[str] = [f"# Incident Run: `{alert.incident_id}`", "", "## Timeline"]

        with start_span(
            "patchnoz.incident.run",
            {
                "incident.id": alert.incident_id,
                "alert.name": alert.alert_name,
                "service.affected": alert.affected_service,
            },
        ) as span:
            try:
                self.recorder.save_alert(alert)
                progress.append(
                    f"- **Alert received**: `{alert.alert_name}` "
                    f"(severity: `{alert.severity}`, service: `{alert.affected_service}`)"
                )

                evidence = self.gateway.collect_evidence(alert)
                incident_run.evidence = evidence
                self.recorder.save_evidence(alert.incident_id, evidence)
                progress.append(f"- **Evidence collected**: {len(evidence.items)} item(s) from SigNoz")
                for item in evidence.items:
                    progress.append(f"  - `[{item.source.upper()}]` {item.summary}")

                root_cause = self.diagnosis_agent.diagnose(alert, evidence)
                incident_run.root_cause = root_cause
                incident_run.status = "diagnosed"
                self.recorder.save_root_cause(alert.incident_id, root_cause)
                progress.append(
                    f"- **Root cause diagnosed**: `{root_cause.suspected_root_cause_service}` "
                    f"(confidence: {root_cause.confidence:.0%})"
                )
                progress.append(f"  - {root_cause.suspected_root_cause}")
                progress.append(f"  - **Recommended fix**: {root_cause.recommended_fix}")

                incident_run.status = "acting"
                actions = self.action_agent.execute(root_cause)
                incident_run.actions = actions
                self.recorder.save_actions(alert.incident_id, actions)
                for action in actions:
                    progress.append(f"- **Action `{action.name}`**: {action.status}")

                incident_run.status = "completed"

            except Exception as e:
                incident_run.status = "failed"
                incident_run.error = str(e)
                span.record_exception(e)
                progress.append(f"- **Run failed**: {e}")

            finally:
                incident_run.end_time = datetime.now(timezone.utc).isoformat()
                self.recorder.save_progress(alert.incident_id, progress)

        flush_telemetry()
        return incident_run
