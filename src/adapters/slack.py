"""
Slack Adapter

Posts an InvestigationResult to Slack via an Incoming Webhook.
The LLM pre-renders slack_one_liner for the alert line; the adapter adds
structure (severity emoji, evidence block, links) around it.

Falls back to a dry-run result when SLACK_WEBHOOK_URL is not configured.
"""

import json
import os
import urllib.error
import urllib.request

from src.env import load_env
from src.models import ActionResult, InvestigationResult

load_env()

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

_SEVERITY_EMOJI = {
    "critical": ":red_circle:",
    "warning": ":large_yellow_circle:",
    "info": ":large_blue_circle:",
}


def build_message(result: InvestigationResult) -> str:
    """Builds the Slack (mrkdwn) message for an InvestigationResult."""
    emoji = _SEVERITY_EMOJI.get(result.severity.lower(), ":white_circle:")
    confidence_bar = _confidence_bar(result.confidence_pct)

    lines = [
        f"{emoji} *PatchNoz incident* | `{result.alert_id}`",
        f"*Alert:* {result.alert_name}  |  *Severity:* `{result.severity}`",
        "",
        f"*{result.slack_one_liner}*",
        "",
        "*Evidence:*",
        f"  • Affected service: `{result.affected_service}` — p99 `{result.affected_service_p99_ms:.0f}ms`",
        f"  • Root cause service: `{result.root_cause_service}` — error rate `{result.root_cause_error_rate_pct:.1f}%`",
    ]

    if result.affected_user_pattern:
        lines.append(f"  • Affected pattern: `{result.affected_user_pattern}`")

    if result.error_message:
        # Truncate long error messages for Slack readability
        msg = result.error_message[:300]
        if len(result.error_message) > 300:
            msg += "..."
        lines += ["", f"*Error observed:*\n```{msg}```"]

    lines += [
        "",
        f"*Confidence:* {confidence_bar} {result.confidence_pct}%",
        f"_{result.confidence_reasoning}_",
        "",
        "*Recommended fix:*",
    ]
    for i, step in enumerate(result.recommended_fix_steps, 1):
        lines.append(f"  {i}. {step}")

    if result.signoz_links:
        lines += ["", "*SigNoz links:*"]
        lines.extend(f"  • <{url}|{_link_label(url)}>" for url in result.signoz_links[:6])

    return "\n".join(lines)


def _confidence_bar(pct: int) -> str:
    filled = round(pct / 10)
    return "█" * filled + "░" * (10 - filled)


def _link_label(url: str) -> str:
    parts = url.rstrip("/").split("/")
    return " › ".join(parts[-2:]) if len(parts) >= 2 else url


def post_summary(result: InvestigationResult) -> ActionResult:
    """Posts the investigation result to Slack, or dry-runs if no webhook is configured."""
    message = build_message(result)

    if not SLACK_WEBHOOK_URL:
        return ActionResult(
            name="slack",
            status="dry_run",
            details={"reason": "SLACK_WEBHOOK_URL not set", "message": message},
        )

    payload = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(
        SLACK_WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        return ActionResult(
            name="slack", status="failed", details={"message": message, "error": str(e)}
        )

    return ActionResult(name="slack", status="success", details={"message": message})
