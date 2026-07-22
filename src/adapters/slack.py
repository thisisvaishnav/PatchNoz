"""
Slack Adapter

Posts a PatchNoz incident diagnosis summary to Slack via an Incoming
Webhook. Falls back to a dry-run result (with the message content
attached) when SLACK_WEBHOOK_URL isn't configured, so the pipeline stays
runnable without any Slack setup.
"""

import json
import os
import urllib.error
import urllib.request

from src.env import load_env
from src.models import ActionResult, RootCauseSummary

load_env()

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")


def build_message(summary: RootCauseSummary) -> str:
    """Builds the Slack (mrkdwn) message body for an incident summary."""
    lines = [
        f"*PatchNoz incident diagnosis:* `{summary.incident_id}`",
        f"Severity: `{summary.severity}` | Affected service: `{summary.affected_service}`",
        f"*Suspected root cause service:* `{summary.suspected_root_cause_service}`",
        summary.suspected_root_cause,
        f"*Recommended fix:* {summary.recommended_fix}",
        f"*Confidence:* {summary.confidence:.0%}",
    ]
    if summary.sig_noz_links:
        lines.append("*SigNoz links:*")
        lines.extend(f"- {url}" for url in summary.sig_noz_links)
    return "\n".join(lines)


def post_summary(summary: RootCauseSummary) -> ActionResult:
    """Posts the incident summary to Slack, or dry-runs it if no webhook is configured."""
    message = build_message(summary)

    if not SLACK_WEBHOOK_URL:
        return ActionResult(
            name="slack",
            status="dry_run",
            details={"reason": "SLACK_WEBHOOK_URL not set", "message": message},
        )

    payload = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(
        SLACK_WEBHOOK_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        return ActionResult(name="slack", status="failed", details={"message": message, "error": str(e)})

    return ActionResult(name="slack", status="success", details={"message": message})
