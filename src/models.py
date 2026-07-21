"""
PatchNoz Domain Models

Defines core objects for incident alerts, evidence, root-cause diagnosis, action results,
and incident execution runs.
"""

import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class IncidentAlert:
    """Represents an incoming incident alert from SigNoz or an external trigger."""
    incident_id: str
    alert_name: str
    severity: str  # e.g., "critical", "warning", "info"
    affected_service: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    description: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IncidentAlert":
        return cls(
            incident_id=data.get("incident_id", ""),
            alert_name=data.get("alert_name", ""),
            severity=data.get("severity", "critical"),
            affected_service=data.get("affected_service", ""),
            timestamp=data.get("timestamp") or datetime.utcnow().isoformat(),
            description=data.get("description"),
            metadata=data.get("metadata", {})
        )


@dataclass
class EvidenceItem:
    """Represents a single piece of telemetry evidence (metric, trace, or log)."""
    source: str  # "metrics", "traces", "logs"
    summary: str
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        res = {"source": self.source, "summary": self.summary}
        if self.details:
            res["details"] = self.details
        return res


@dataclass
class IncidentEvidence:
    """Represents all collected evidence for an incident."""
    incident_id: str
    affected_service: str
    evidence_items: List[EvidenceItem] = field(default_factory=list)
    metrics_anomalies: List[Dict[str, Any]] = field(default_factory=list)
    traces_summary: List[Dict[str, Any]] = field(default_factory=list)
    logs_summary: List[Dict[str, Any]] = field(default_factory=list)
    suspected_services: List[str] = field(default_factory=list)

    def add_evidence(self, source: str, summary: str, details: Optional[Dict[str, Any]] = None):
        self.evidence_items.append(EvidenceItem(source=source, summary=summary, details=details))

    def get_summary_list(self) -> List[Dict[str, str]]:
        return [{"source": item.source, "summary": item.summary} for item in self.evidence_items]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "affected_service": self.affected_service,
            "evidence": self.get_summary_list(),
            "metrics_anomalies": self.metrics_anomalies,
            "traces_summary": self.traces_summary,
            "logs_summary": self.logs_summary,
            "suspected_services": self.suspected_services
        }


@dataclass
class RootCauseSummary:
    """
    Represents the diagnosis output for an incident.
    Matches the standard minimum useful JSON handoff shape.
    """
    incident_id: str
    alert_name: str
    severity: str
    affected_service: str
    suspected_root_cause_service: str
    suspected_root_cause: str
    evidence: List[Dict[str, str]] = field(default_factory=list)
    recommended_fix: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "alert_name": self.alert_name,
            "severity": self.severity,
            "affected_service": self.affected_service,
            "suspected_root_cause_service": self.suspected_root_cause_service,
            "suspected_root_cause": self.suspected_root_cause,
            "evidence": self.evidence,
            "recommended_fix": self.recommended_fix
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RootCauseSummary":
        return cls(
            incident_id=data.get("incident_id", ""),
            alert_name=data.get("alert_name", ""),
            severity=data.get("severity", "critical"),
            affected_service=data.get("affected_service", ""),
            suspected_root_cause_service=data.get("suspected_root_cause_service", ""),
            suspected_root_cause=data.get("suspected_root_cause", ""),
            evidence=data.get("evidence", []),
            recommended_fix=data.get("recommended_fix", "")
        )


@dataclass
class ActionResult:
    """Represents the outcome of an automated action (Slack, GitHub PR, SigNoz Dashboard)."""
    action_type: str  # "slack", "github_pr", "signoz_dashboard"
    success: bool
    summary: str
    url: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IncidentRun:
    """Represents an entire execution lifecycle for an incident."""
    run_id: str
    incident_id: str
    alert: IncidentAlert
    evidence: Optional[IncidentEvidence] = None
    root_cause: Optional[RootCauseSummary] = None
    actions: List[ActionResult] = field(default_factory=list)
    status: str = "initialized"  # "initialized", "diagnosing", "diagnosed", "acting", "completed", "failed"
    start_time: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    end_time: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "incident_id": self.incident_id,
            "alert": self.alert.to_dict(),
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "root_cause": self.root_cause.to_dict() if self.root_cause else None,
            "actions": [a.to_dict() for a in self.actions],
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "error": self.error
        }
