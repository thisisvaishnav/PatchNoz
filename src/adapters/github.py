"""
GitHub Adapter

Opens a GitHub issue from an InvestigationResult, with deduplication:
find_open_issue() searches GitHub for an existing open issue tagged with
the same service and alert name before creating a new one.

The LLM pre-renders github_body (full markdown), so the adapter only
handles the title construction, label tagging, and API calls.

Falls back to a dry-run result when credentials are not configured.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from src.env import load_env
from src.models import ActionResult, InvestigationResult

load_env()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")
GITHUB_API_URL = "https://api.github.com"


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _alert_label(result: InvestigationResult) -> str:
    """Stable label that identifies this alert across scan cycles."""
    safe = result.alert_name.lower().replace(" ", "-").replace("_", "-")[:40]
    return f"patchnoz:{result.affected_service}:{safe}"


def find_open_issue(result: InvestigationResult) -> Optional[str]:
    """
    Search GitHub for an open PatchNoz issue for this service/alert.
    Returns the issue HTML URL if one exists, None otherwise.

    This is the deduplication check: if an issue is already open, the
    scan cycle skips creating a new one.
    """
    if not (GITHUB_TOKEN and GITHUB_OWNER and GITHUB_REPO):
        return None

    label = _alert_label(result)
    query = urllib.parse.urlencode({
        "q": f"repo:{GITHUB_OWNER}/{GITHUB_REPO} is:issue is:open label:{label}",
        "per_page": "1",
    })
    url = f"{GITHUB_API_URL}/search/issues?{query}"
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data: Dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        items = data.get("items", [])
        if items:
            return items[0].get("html_url")
    except (urllib.error.URLError, urllib.error.HTTPError):
        pass
    return None


def build_issue(result: InvestigationResult) -> Dict[str, str]:
    """Build the {title, body, labels} payload for a GitHub issue."""
    title = (
        f"[PatchNoz] {result.affected_service}: "
        f"{result.alert_name} (root cause: {result.root_cause_service})"
    )
    # The LLM wrote the body; we prepend a metadata header for at-a-glance scanning
    header_lines = [
        f"| Field | Value |",
        f"|---|---|",
        f"| **Alert** | `{result.alert_id}` |",
        f"| **Severity** | `{result.severity}` |",
        f"| **Affected service** | `{result.affected_service}` |",
        f"| **Root cause service** | `{result.root_cause_service}` |",
        f"| **Confidence** | {result.confidence_pct}% |",
        f"| **Model** | `{result.model}` |",
        f"| **Tool calls** | {result.tool_calls_made} |",
        "",
        "_Investigation by [PatchNoz](https://github.com/thisisvaishnav/PatchNoz)_",
        "",
        "---",
        "",
        result.github_body,
    ]
    return {
        "title": title,
        "body": "\n".join(header_lines),
        "labels": ["patchnoz", _alert_label(result)],
    }


def _ensure_labels_exist() -> None:
    """Create the 'patchnoz' label if it doesn't already exist."""
    url = f"{GITHUB_API_URL}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/labels"
    payload = json.dumps({"name": "patchnoz", "color": "7057ff", "description": "Created by PatchNoz"}).encode()
    req = urllib.request.Request(url, data=payload, headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except urllib.error.HTTPError as e:
        if e.code != 422:  # 422 = label already exists, which is fine
            pass


def create_issue(result: InvestigationResult) -> ActionResult:
    """
    Creates a GitHub issue, or dry-runs if credentials are not configured.

    Skips creation if find_open_issue() finds an existing open issue (the
    caller -- ScanOrchestrator -- should already have checked this, but we
    guard here too for direct calls).
    """
    issue = build_issue(result)

    if not (GITHUB_TOKEN and GITHUB_OWNER and GITHUB_REPO):
        return ActionResult(
            name="github",
            status="dry_run",
            details={
                "reason": "GITHUB_TOKEN/GITHUB_OWNER/GITHUB_REPO not fully configured",
                "title": issue["title"],
                "body": issue["body"],
            },
        )

    _ensure_labels_exist()

    # Ensure the per-alert label exists too
    label = _alert_label(result)
    label_payload = json.dumps({"name": label, "color": "e4e669"}).encode()
    lreq = urllib.request.Request(
        f"{GITHUB_API_URL}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/labels",
        data=label_payload,
        headers=_headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(lreq, timeout=10):
            pass
    except urllib.error.HTTPError:
        pass  # label already exists or insufficient permissions

    url = f"{GITHUB_API_URL}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/issues"
    payload = json.dumps({
        "title": issue["title"],
        "body": issue["body"],
        "labels": issue["labels"],
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data: Dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return ActionResult(
            name="github",
            status="failed",
            details={"title": issue["title"], "error": f"HTTP {e.code}: {e.reason}", "response_body": body},
        )
    except urllib.error.URLError as e:
        return ActionResult(
            name="github",
            status="failed",
            details={"title": issue["title"], "error": str(e)},
        )

    return ActionResult(
        name="github",
        status="success",
        url=data.get("html_url"),
        details={"issue_number": data.get("number"), "title": issue["title"]},
    )
