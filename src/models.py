"""
PatchNoz Domain Models

Plain dataclasses for the objects that flow through the PatchNoz pipeline.

InvestigationResult replaces the old RootCauseSummary: it is produced by the
LLM investigation agent and contains real evidence values (specific error
messages, actual p99 numbers, affected user patterns) rather than hardcoded
template sentences.

EvidenceItem and IncidentEvidence are removed -- the LLM agent decides what
to query and reasons directly over raw tool responses.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_service_from_generator_url(gen_url: str) -> str:
    if not gen_url or not isinstance(gen_url, str):
        return ""
    try:
        decoded_url = unquote(gen_url)
        parsed = urlparse(decoded_url)
        params = parse_qs(parsed.query)
        service_list = params.get("service_name") or params.get("service")
        if service_list and len(service_list) > 0:
            return service_list[0]
    except Exception:
        pass
    return ""


@dataclass
class IncidentAlert:
    """An incoming SigNoz alert -- the unit of work that triggers an Investigation."""
    incident_id: str
    alert_name: str
    severity: str           # "critical", "warning", "info"
    affected_service: str
    condition: str = ""     # e.g. "p99 latency > 1s"
    time_range: str = "15m"
    suspected_area: str = ""
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

    @classmethod
    def from_signoz_alert(cls, raw: Dict[str, Any]) -> "IncidentAlert":
        """Construct an IncidentAlert from a SigNoz list_alerts row."""
        labels = raw.get("labels", {})
        gen_url = raw.get("generatorURL", "")
        service = (
            labels.get("service_name")
            or labels.get("service")
            or extract_service_from_generator_url(gen_url)
            or "unknown"
        )
        alert_name = raw.get("name") or raw.get("alertname") or labels.get("alertname", "unknown-alert")
        severity = (labels.get("severity") or raw.get("severity") or "warning").lower()
        incident_id = f"{service}-{alert_name}".lower().replace(" ", "-").replace("_", "-")
        return cls(
            incident_id=incident_id,
            alert_name=alert_name,
            severity=severity,
            affected_service=service,
            condition=raw.get("annotations", {}).get("description", ""),
        )


@dataclass
class InvestigationResult:
    """
    Structured output produced by the LLM investigation agent for one Alert.

    Every field is grounded in evidence the agent actually observed -- no
    template sentences. slack_one_liner and github_body are pre-rendered by
    the LLM so the adapters just forward them.
    """
    alert_id: str
    alert_name: str
    severity: str
    affected_service: str
    root_cause_service: str
    error_message: str                          # exact text from traces/logs
    affected_user_pattern: str                  # e.g. "gold-tier loyalty users", or ""
    affected_service_p99_ms: float              # actual measured value
    root_cause_error_rate_pct: float            # actual measured value
    confidence_pct: int                         # 0-100
    confidence_reasoning: str                   # why this confidence, citing evidence
    recommended_fix_steps: List[str]            # 2-5 concrete steps
    slack_one_liner: str                        # <120 chars, specific numbers
    github_body: str                            # full markdown for GitHub issue body
    signoz_links: List[str] = field(default_factory=list)
    tool_calls_made: int = 0
    model: str = ""
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class ActionResult:
    """The outcome of a single Action (Slack post or GitHub issue)."""
    name: str           # "slack", "github"
    status: str         # "success", "dry_run", "failed"
    url: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IncidentRun:
    """The full execution record for one incident investigation."""
    alert: IncidentAlert
    result: Optional[InvestigationResult] = None
    actions: List[ActionResult] = field(default_factory=list)
    status: str = "initialized"     # initialized, investigating, acting, completed, failed
    start_time: str = field(default_factory=_now_iso)
    end_time: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.alert.incident_id,
            "alert": self.alert.to_dict(),
            "result": self.result.to_dict() if self.result else None,
            "actions": [a.to_dict() for a in self.actions],
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "error": self.error,
        }
