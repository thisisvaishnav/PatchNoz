"""
Run Recorder

Persists per-incident run artifacts to disk:

    runs/<incident_id>/alert.json
    runs/<incident_id>/result.json      (InvestigationResult)
    runs/<incident_id>/actions.json
    runs/<incident_id>/progress.md

Call start() when a run begins, update() after each phase, finish() at the end.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from src.models import ActionResult, IncidentAlert, IncidentRun


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunRecorder:
    """Saves run artifacts under `<base_dir>/<incident_id>/`."""

    def __init__(self, base_dir: str = "runs"):
        self.base_dir = Path(base_dir)

    # --- Lifecycle methods called by orchestrators ---

    def start(self, run: IncidentRun) -> None:
        """Write the initial alert.json when a run begins."""
        self._write_json(run.alert.incident_id, "alert.json", run.alert.to_dict())
        self._write_progress(run)

    def update(self, run: IncidentRun) -> None:
        """Flush current run state to disk (called after each phase change)."""
        self._write_progress(run)

    def finish(self, run: IncidentRun) -> None:
        """Write all final artifacts once the run is complete or failed."""
        iid = run.alert.incident_id
        if run.result:
            self._write_json(iid, "result.json", run.result.to_dict())
        if run.actions:
            self._write_json(iid, "actions.json", [a.to_dict() for a in run.actions])
        self._write_progress(run)

    # --- Lower-level helpers (used by old orchestrator path and tests) ---

    def save_alert(self, alert: IncidentAlert) -> Path:
        return self._write_json(alert.incident_id, "alert.json", alert.to_dict())

    def save_actions(self, incident_id: str, actions: List[ActionResult]) -> Path:
        return self._write_json(incident_id, "actions.json", [a.to_dict() for a in actions])

    # --- Internals ---

    def _write_progress(self, run: IncidentRun) -> None:
        iid = run.alert.incident_id
        result = run.result
        lines = [
            f"# PatchNoz run: {iid}",
            "",
            f"**Status:** {run.status}",
            f"**Alert:** {run.alert.alert_name}",
            f"**Service:** {run.alert.affected_service}",
            f"**Severity:** {run.alert.severity}",
            f"**Started:** {run.start_time}",
        ]
        if run.end_time:
            lines.append(f"**Ended:** {run.end_time}")
        if result:
            lines += [
                "",
                "## Investigation result",
                f"- Root cause service: `{result.root_cause_service}`",
                f"- Confidence: {result.confidence_pct}%",
                f"- Reasoning: {result.confidence_reasoning}",
                f"- Tool calls made: {result.tool_calls_made}",
                f"- Model: {result.model}",
            ]
            if result.error_message:
                lines += ["", f"**Error observed:** `{result.error_message[:200]}`"]
            if result.recommended_fix_steps:
                lines += ["", "## Recommended fix steps"]
                lines.extend(f"- [ ] {s}" for s in result.recommended_fix_steps)
        if run.actions:
            lines += ["", "## Actions"]
            for a in run.actions:
                status_icon = {"success": "✅", "dry_run": "🔵", "failed": "❌"}.get(a.status, "?")
                url_part = f" → {a.url}" if a.url else ""
                lines.append(f"- {status_icon} **{a.name}**: {a.status}{url_part}")
        if run.error:
            lines += ["", f"**Error:** {run.error}"]

        path = self._run_dir(iid) / "progress.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _run_dir(self, incident_id: str) -> Path:
        run_dir = self.base_dir / incident_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _write_json(self, incident_id: str, filename: str, data) -> Path:
        path = self._run_dir(incident_id) / filename
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path
