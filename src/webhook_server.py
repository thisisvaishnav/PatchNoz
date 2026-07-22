"""
SigNoz Alert Webhook Receiver

A real alternate entry point into the investigation pipeline: instead of
only simulating an alert via `run_patchnoz.py --scenario ...`, this exposes
an HTTP endpoint that a SigNoz "Webhook" notification channel can call
directly the moment a rule fires.

SigNoz's Webhook channel POSTs a Prometheus Alertmanager-shaped payload:

    {
      "receiver": "patchnoz",
      "status": "firing",
      "alerts": [
        {
          "status": "firing",
          "labels": {"alertname": "...", "severity": "critical", "service_name": "..."},
          "annotations": {"description": "..."},
          "startsAt": "2024-01-01T00:00:00Z",
          "endsAt": "0001-01-01T00:00:00Z",
          "generatorURL": "...",
          "fingerprint": "..."
        }
      ],
      "groupLabels": {...},
      "commonLabels": {...},
      "commonAnnotations": {...},
      "externalURL": "...",
      "version": "4",
      "groupKey": "..."
    }

Each entry in `alerts` maps 1:1 onto IncidentAlert.from_signoz_alert() --
the same parser the periodic ScanOrchestrator already uses. Only alerts
with status == "firing" are investigated; "resolved" alerts are
acknowledged and skipped.

Investigations run on a background thread so the HTTP response returns
immediately: SigNoz/Alertmanager webhook receivers have a short send
timeout and will retry on a slow response, and a single alert can take
many seconds (LLM tool-calling loop + Slack/GitHub calls). The response
only confirms an alert was *accepted*, not that the investigation finished
-- follow up via runs/<incident_id>/progress.md, or the Slack/GitHub
actions it produces.

Reuses ScanOrchestrator.handle_alert() for the actual dedupe -> investigate
-> act -> record pipeline, so a webhook-delivered alert that already has an
open GitHub issue is skipped exactly like it would be in scan mode.
"""

import os
import threading
import traceback
from typing import Any, Dict, List

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from src.env import load_env
from src.models import IncidentAlert
from src.scan_orchestrator import ScanOrchestrator

load_env()

WEBHOOK_TOKEN = os.getenv("PATCHNOZ_WEBHOOK_TOKEN", "")

# One shared orchestrator so webhook-triggered investigations use the same
# LLM/action/recorder wiring -- and GitHub-issue dedup -- as the periodic scan.
_orchestrator = ScanOrchestrator()


def _is_authorized(request: Request) -> bool:
    """
    If PATCHNOZ_WEBHOOK_TOKEN is unset, the endpoint is unauthenticated --
    fine for local/demo use behind a trusted network, matching this
    project's "runs end-to-end even with nothing configured" philosophy.

    If it is set, the caller must present it via the
    X-PatchNoz-Webhook-Token header (SigNoz's Webhook channel supports
    custom headers) or a `token` query parameter.
    """
    if not WEBHOOK_TOKEN:
        return True
    provided = request.headers.get("x-patchnoz-webhook-token") or request.query_params.get("token")
    return provided == WEBHOOK_TOKEN


def _extract_alerts(payload: Any) -> List[Dict[str, Any]]:
    """
    Normalizes the request body into a list of raw per-alert dicts.

    Accepts:
      - SigNoz/Alertmanager batch shape: {"alerts": [...], "status": ...}
      - A single alert dict posted directly (handy for manual/curl testing).
    """
    if not isinstance(payload, dict):
        return []
    alerts = payload.get("alerts")
    if isinstance(alerts, list):
        return [a for a in alerts if isinstance(a, dict)]
    if "labels" in payload or "alertname" in payload or "name" in payload:
        return [payload]
    return []


def _investigate_in_background(alert: IncidentAlert) -> None:
    try:
        _orchestrator.handle_alert(alert)
    except Exception:
        print(f"[webhook_server] Investigation crashed for {alert.incident_id}:")
        traceback.print_exc()


async def signoz_webhook(request: Request) -> JSONResponse:
    """POST /webhook/signoz -- entry point for a real SigNoz Webhook channel."""
    if not _is_authorized(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)

    raw_alerts = _extract_alerts(payload)
    if not raw_alerts:
        return JSONResponse(
            {"error": "no alerts found in payload (expected an 'alerts' list, or a single alert object)"},
            status_code=400,
        )

    accepted: List[str] = []
    skipped_resolved = 0
    errors: List[str] = []

    for raw in raw_alerts:
        status = str(raw.get("status") or "firing").lower()
        if status != "firing":
            skipped_resolved += 1
            continue
        try:
            alert = IncidentAlert.from_signoz_alert(raw)
        except Exception as exc:
            errors.append(str(exc))
            continue

        accepted.append(alert.incident_id)
        print(f"[webhook_server] Accepted alert: {alert.incident_id} ({alert.affected_service})")
        threading.Thread(
            target=_investigate_in_background, args=(alert,), daemon=True
        ).start()

    return JSONResponse(
        {"accepted": accepted, "skipped_resolved": skipped_resolved, "errors": errors},
        status_code=202,
    )


async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


app = Starlette(
    routes=[
        Route("/webhook/signoz", signoz_webhook, methods=["POST"]),
        Route("/healthz", healthz, methods=["GET"]),
    ]
)
