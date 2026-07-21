"""
Run Recorder

Saves progress and artifacts per run into specified output directory.
Produces alert.json, evidence.json, root_cause.json, and progress.md.
"""

import json
import os
from typing import Optional, Dict
from src.models import IncidentAlert, IncidentEvidence, RootCauseSummary


class RunRecorder:
    """Handles saving run artifacts and formatting progress logs."""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir

    def ensure_dir(self):
        """Ensures destination directory exists."""
        os.makedirs(self.output_dir, exist_ok=True)

    def save_alert(self, alert: IncidentAlert) -> str:
        """Saves alert.json."""
        self.ensure_dir()
        file_path = os.path.join(self.output_dir, "alert.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(alert.to_dict(), f, indent=2)
        return file_path

    def save_evidence(self, evidence: IncidentEvidence) -> str:
        """Saves evidence.json."""
        self.ensure_dir()
        file_path = os.path.join(self.output_dir, "evidence.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(evidence.to_dict(), f, indent=2)
        return file_path

    def save_root_cause(self, root_cause: RootCauseSummary) -> str:
        """Saves root_cause.json."""
        self.ensure_dir()
        file_path = os.path.join(self.output_dir, "root_cause.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(root_cause.to_dict(), f, indent=2)
        return file_path

    def save_progress_md(self, alert: IncidentAlert, evidence: Optional[IncidentEvidence] = None, root_cause: Optional[RootCauseSummary] = None) -> str:
        """Generates and saves progress.md timeline."""
        self.ensure_dir()
        file_path = os.path.join(self.output_dir, "progress.md")

        lines = [
            f"# Incident Run Progress: `{alert.incident_id}`",
            "",
            "## Timeline",
            f"- **Alert Triggered**: `{alert.alert_name}` (Severity: `{alert.severity}`, Service: `{alert.affected_service}`)",
        ]

        if evidence:
            lines.extend([
                f"- **Telemetry Collected**: Gathered evidence across metrics, traces, and logs.",
                f"  - **Suspected Services**: {', '.join(evidence.suspected_services) if evidence.suspected_services else alert.affected_service}",
                f"  - **Metrics Anomalies Count**: {len(evidence.metrics_anomalies)}",
                f"  - **Traces Analyzed**: {len(evidence.traces_summary)}",
                f"  - **Logs Analyzed**: {len(evidence.logs_summary)}",
            ])

        if root_cause:
            lines.extend([
                f"- **Root Cause Diagnosed**: `{root_cause.suspected_root_cause_service}`",
                f"  - **Explanation**: {root_cause.suspected_root_cause}",
                f"  - **Recommended Fix**: {root_cause.recommended_fix}",
            ])

        lines.extend([
            "",
            "## Evidence Summary",
        ])

        if evidence and evidence.evidence_items:
            for item in evidence.evidence_items:
                lines.append(f"- `[{item.source.upper()}]` {item.summary}")
        else:
            lines.append("No evidence items collected yet.")

        lines.append("")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return file_path

    def save_all(self, alert: IncidentAlert, evidence: IncidentEvidence, root_cause: RootCauseSummary) -> Dict[str, str]:
        """Saves all run artifacts and returns file paths."""
        return {
            "alert": self.save_alert(alert),
            "evidence": self.save_evidence(evidence),
            "root_cause": self.save_root_cause(root_cause),
            "progress": self.save_progress_md(alert, evidence, root_cause)
        }
