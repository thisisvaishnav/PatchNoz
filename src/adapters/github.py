"""
GitHub Adapter

Opens a GitHub issue describing a diagnosed incident and its suggested
fix. Falls back to a dry-run result (with the title/body attached) when
GITHUB_TOKEN/GITHUB_OWNER/GITHUB_REPO aren't fully configured.

Opening a full PR with a code diff is a stretch goal and intentionally
not implemented yet - it does not block the PatchNoz MVP.
"""

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict

from src.env import load_env
from src.models import ActionResult, RootCauseSummary

load_env()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")
GITHUB_API_URL = "https://api.github.com"


def build_issue(summary: RootCauseSummary) -> Dict[str, str]:
    """Builds the {title, body} payload for a GitHub issue describing the incident."""
    title = (
        f"[PatchNoz] {summary.affected_service}: "
        f"{summary.suspected_root_cause_service} incident {summary.incident_id}"
    )
    body_lines = [
        f"**Incident:** `{summary.incident_id}`",
        f"**Severity:** `{summary.severity}`",
        f"**Affected service:** `{summary.affected_service}`",
        f"**Suspected root cause service:** `{summary.suspected_root_cause_service}`",
        "",
        "### Suspected root cause",
        summary.suspected_root_cause,
        "",
        "### Recommended fix",
        summary.recommended_fix,
        "",
        f"_Confidence: {summary.confidence:.0%}_",
    ]
    if summary.sig_noz_links:
        body_lines += ["", "### SigNoz links"] + [f"- {url}" for url in summary.sig_noz_links]
    return {"title": title, "body": "\n".join(body_lines)}


def create_issue(summary: RootCauseSummary) -> ActionResult:
    """Creates a GitHub issue with the suggested fix, or dry-runs it if unconfigured."""
    issue = build_issue(summary)

    if not (GITHUB_TOKEN and GITHUB_OWNER and GITHUB_REPO):
        return ActionResult(
            name="github",
            status="dry_run",
            details={
                "reason": "GITHUB_TOKEN/GITHUB_OWNER/GITHUB_REPO not fully configured",
                **issue,
            },
        )

    url = f"{GITHUB_API_URL}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/issues"
    payload = json.dumps(issue).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data: Dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return ActionResult(
            name="github",
            status="failed",
            details={**issue, "error": f"HTTP {e.code}: {e.reason}", "response_body": body},
        )
    except urllib.error.URLError as e:
        return ActionResult(name="github", status="failed", details={**issue, "error": str(e)})

    return ActionResult(
        name="github",
        status="success",
        url=data.get("html_url"),
        details={"issue_number": data.get("number"), **issue},
    )
