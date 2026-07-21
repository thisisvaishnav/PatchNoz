"""
PatchNoz Domain Models

Plain dataclasses (standard library only) for the objects that flow through
the PatchNoz pipeline: an incoming alert, the evidence collected about it,
the diagnosed root cause, the actions taken, and the run that ties them
all together.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class IncidentAlert:
    """An incoming (or simulated) SigNoz alert."""
    incident_id: str
    alert_name: str
    severity: str  # "critical", "warning", "info"
    affected_service: str
    condition: str = ""  # e.g. "p99 latency > 1s"
    time_range: str = "15m"
    suspected_area: str = ""  # e.g. a suspected downstream dependency
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IncidentAlert":
        return cls(
            incident_id=data.get("incident_id", ""),
            alert_name=data.get("alert_name", ""),
            severity=data.get("severity", "critical"),
            affected_service=data.get("affected_service", ""),
            condition=data.get("condition", ""),
            time_range=data.get("time_range", "15m"),
            suspected_area=data.get("suspected_area", ""),
            timestamp=data.get("timestamp") or _now_iso(),
        )


@dataclass
class EvidenceItem:
    """A single normalized piece of telemetry evidence."""
    source: str  # "metrics", "traces", "logs", "error"
    service: str
    summary: str
    raw: Any = None
    url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "service": self.service,
            "summary": self.summary,
            "raw": self.raw,
            "url": self.url,
        }


@dataclass
class IncidentEvidence:
    """All evidence collected for an incident."""
    incident_id: str
    items: List[EvidenceItem] = field(default_factory=list)

    def add(self, item: EvidenceItem) -> None:
        self.items.append(item)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass
class RootCauseSummary:
    """The diagnosis output for an incident."""
    incident_id: str
    severity: str
    affected_service: str
    suspected_root_cause_service: str
    suspected_root_cause: str
    evidence: List[EvidenceItem] = field(default_factory=list)
    recommended_fix: str = ""
    confidence: float = 0.5
    sig_noz_links: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "severity": self.severity,
            "affected_service": self.affected_service,
            "suspected_root_cause_service": self.suspected_root_cause_service,
            "suspected_root_cause": self.suspected_root_cause,
            "evidence": [item.to_dict() for item in self.evidence],
            "recommended_fix": self.recommended_fix,
            "confidence": self.confidence,
            "sig_noz_links": self.sig_noz_links,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class ActionResult:
    """The outcome of a single remediation action (Slack, GitHub, ...)."""
    name: str  # "slack", "github"
    status: str  # "success", "dry_run", "failed"
    url: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IncidentRun:
    """The full execution lifecycle for one incident."""
    alert: IncidentAlert
    evidence: Optional[IncidentEvidence] = None
    root_cause: Optional[RootCauseSummary] = None
    actions: List[ActionResult] = field(default_factory=list)
    status: str = "initialized"  # initialized, diagnosing, diagnosed, acting, completed, failed
    start_time: str = field(default_factory=_now_iso)
    end_time: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.alert.incident_id,
            "alert": self.alert.to_dict(),
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "root_cause": self.root_cause.to_dict() if self.root_cause else None,
            "actions": [a.to_dict() for a in self.actions],
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "error": self.error,
        }
