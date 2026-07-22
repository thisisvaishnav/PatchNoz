"""
Create a SigNoz metric-based alert rule for payment service error rate.
Uses the v5 compositeQuery schema (queries array with typed envelopes).
"""

import json
import sys
import urllib.error
import urllib.request

BASE_URL = "http://localhost:8080"
EMAIL    = "vaishnav.verma.cs28@iilm.edu"
PASSWORD = "password"
ORG_ID   = "019f8442-98bb-7410-a3fb-1183140fa210"

RULE_NAME = "PaymentServiceHighErrorRate"

PROM_QUERY = (
    'sum(rate(signoz_calls_total{service_name="payment",status_code="STATUS_CODE_ERROR"}[5m]))'
    " / "
    'sum(rate(signoz_calls_total{service_name="payment"}[5m]))'
)


def login() -> str:
    payload = json.dumps({"email": EMAIL, "password": PASSWORD, "orgID": ORG_ID}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/v2/sessions/email_password",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        token = json.loads(r.read())["data"]["accessToken"]
    print(f"[auth] OK — token prefix: {token[:30]}…")
    return token


def hdrs(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def api(token: str, method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, headers=hdrs(token), method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode()}") from exc


def existing_rule_names(token: str) -> set:
    data = api(token, "GET", "/api/v1/rules")
    rules = []
    if isinstance(data, list):
        rules = data
    elif isinstance(data, dict):
        inner = data.get("data", data)
        rules = inner.get("rules", []) if isinstance(inner, dict) else inner
    names = set()
    for r in rules if isinstance(rules, list) else []:
        if isinstance(r, dict):
            n = r.get("alert") or r.get("name") or ""
            names.add(n.lower())
    print(f"[rules] {len(names)} existing rule(s): {names or '(none)'}")
    return names


def build_rule() -> dict:
    """
    v5 schema alert rule.

    compositeQuery.queries is an array of QueryEnvelope objects:
      { "type": "promql", "spec": { PromQuery fields } }

    condition.op and condition.matchType are numeric strings:
      "1" = above (gt) / at-least-once
    condition.target is a float.

    version MUST be "v5".
    """
    return {
        "alert":        RULE_NAME,
        "alertType":    "METRIC_BASED_ALERT",
        "version":      "v5",
        "disabled":     False,
        "broadcastToAll": True,
        "preferredChannels": ["patchnoz-slack"],
        "evalWindow": "5m0s",
        "frequency":  "1m0s",
        "labels": {
            "service_name": "payment",
            "severity":     "critical",
            "team":         "payments",
        },
        "annotations": {
            "description": "Payment service error rate is above 5% for 5 minutes.",
            "summary":     "Payment service high error rate",
        },
        "condition": {
            "compositeQuery": {
                "queries": [
                    {
                        "type": "promql",
                        "spec": {
                            "name":     "A",
                            "query":    PROM_QUERY,
                            "disabled": False,
                            "step":     60,
                            "legend":   "error_rate",
                        },
                    }
                ]
            },
            "op":        "1",
            "target":    0.05,
            "matchType": "1",
        },
    }


if __name__ == "__main__":
    token = login()

    names = existing_rule_names(token)
    if RULE_NAME.lower() in names:
        print(f"[rules] '{RULE_NAME}' already exists — nothing to do.")
        sys.exit(0)

    rule = build_rule()
    print(f"\n[rules] Creating '{RULE_NAME}' …")
    print("Payload:", json.dumps(rule, indent=2))
    try:
        resp = api(token, "POST", "/api/v1/rules", rule)
        rule_id = (resp.get("data") or {}).get("id") or resp.get("id") or "?"
        print(f"\n[rules] Created! ID={rule_id}")
        print(json.dumps(resp, indent=2))
    except RuntimeError as exc:
        print(f"\n[rules] FAILED: {exc}")
        sys.exit(1)
