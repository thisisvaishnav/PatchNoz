"""
Run Recorder

Persists per-incident run artifacts to disk so a run can be inspected,
diffed, or replayed after the fact:

    runs/<incident_id>/alert.json
    runs/<incident_id>/evidence.json
    runs/<incident_id>/root_cause.json
    runs/<incident_id>/actions.json
    runs/<incident_id>/progress.md
"""

import json
from pathlib import Path
from typing import List

from src.models import ActionResult, IncidentAlert, IncidentEvidence, RootCauseSummary


class RunRecorder:
    """Saves run artifacts under `<base_dir>/<incident_id>/`."""

    def __init__(self, base_dir: str = "runs"):
        self.base_dir = Path(base_dir)

    def save_alert(self, alert: IncidentAlert) -> Path:
        return self._write_json(alert.incident_id, "alert.json", alert.to_dict())

    def save_evidence(self, incident_id: str, evidence: IncidentEvidence) -> Path:
        return self._write_json(incident_id, "evidence.json", evidence.to_dict())

    def save_root_cause(self, incident_id: str, summary: RootCauseSummary) -> Path:
        return self._write_json(incident_id, "root_cause.json", summary.to_dict())

    def save_actions(self, incident_id: str, actions: List[ActionResult]) -> Path:
        return self._write_json(incident_id, "actions.json", [a.to_dict() for a in actions])

    def save_progress(self, incident_id: str, lines: List[str]) -> Path:
        path = self._run_dir(incident_id) / "progress.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    # --- Internals ---

    def _run_dir(self, incident_id: str) -> Path:
        run_dir = self.base_dir / incident_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _write_json(self, incident_id: str, filename: str, data) -> Path:
        path = self._run_dir(incident_id) / filename
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path
