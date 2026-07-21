"""
Incident Orchestrator

Owns the full incident resolution pipeline:
Alert -> TelemetryGateway -> DiagnosisAgent -> RunRecorder -> Self-Observability Traces.
"""

from typing import Optional
from src.models import IncidentAlert, IncidentRun, IncidentEvidence, RootCauseSummary
from src.telemetry_gateway import TelemetryGateway
from src.diagnosis_agent import DiagnosisAgent
from src.run_recorder import RunRecorder
from src.self_telemetry import trace_span, flush_telemetry


class IncidentOrchestrator:
    """
    Orchestrates evidence collection, root-cause diagnosis, action execution,
    artifact recording, and self-telemetry tracing for an incident.
    """

    def __init__(
        self,
        gateway: Optional[TelemetryGateway] = None,
        diagnosis_agent: Optional[DiagnosisAgent] = None
    ):
        self.gateway = gateway or TelemetryGateway()
        self.diagnosis_agent = diagnosis_agent or DiagnosisAgent()

    def run(self, alert: IncidentAlert, output_dir: str) -> IncidentRun:
        """
        Executes a complete incident diagnosis run for the given alert.

        Args:
            alert: IncidentAlert instance describing the alert.
            output_dir: Path to directory where run artifacts will be saved.

        Returns:
            IncidentRun domain model containing execution details and results.
        """
        recorder = RunRecorder(output_dir)
        incident_run = IncidentRun(
            run_id=f"run-{alert.incident_id}",
            incident_id=alert.incident_id,
            alert=alert,
            status="diagnosing"
        )

        with trace_span("orchestrator.run", {"incident_id": alert.incident_id, "service": alert.affected_service}):
            # Step 1: Save initial alert artifact
            recorder.save_alert(alert)

            # Step 2: Collect evidence from SigNoz via TelemetryGateway
            with trace_span("telemetry.collect_evidence", {"affected_service": alert.affected_service}):
                evidence: IncidentEvidence = self.gateway.collect_evidence(alert)
                incident_run.evidence = evidence

            # Step 3: Diagnose root cause via DiagnosisAgent
            with trace_span("diagnosis.diagnose", {"incident_id": alert.incident_id}):
                root_cause: RootCauseSummary = self.diagnosis_agent.diagnose(alert, evidence)
                incident_run.root_cause = root_cause
                incident_run.status = "diagnosed"

            # Step 4: Record run artifacts (evidence.json, root_cause.json, progress.md)
            with trace_span("recorder.save_artifacts", {"output_dir": output_dir}):
                recorder.save_all(alert, evidence, root_cause)

            incident_run.status = "completed"

        # Step 5: Flush OTel spans so they reach SigNoz
        flush_telemetry()

        return incident_run
