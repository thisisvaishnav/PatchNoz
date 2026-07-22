# PatchNoz Project Progress

Legend: `[x]` verified working end-to-end, `[~]` code complete but not yet
exercised with real credentials, `[ ]` not started.

## Demo Scenario

- [x] Scenario chosen: `checkout-payment-latency`
- [x] OpenTelemetry Demo running (verified: real `oteldemo.PaymentService/Charge`
      traces, real payment log fields like `transactionId`/`cardType`/`amount`
      show up in `runs/demo-checkout-payment/evidence.json`)
- [x] SigNoz running at http://localhost:8080 (verified: `200 OK`, live
      service list returned via `SigNozMCPAdapter.list_services()`)
- [x] SigNoz MCP running at http://localhost:8000/mcp (verified: adapter
      authenticates and pulls real traces/logs/metrics through it)
- [x] PatchNoz self-traces visible in SigNoz (verified: `patchnoz-agent`
      appears in `list_services()`, and its spans are retrievable via
      `search_traces('patchnoz-agent')`)

## Milestone 1 — Demo Spine

- [x] `src/models.py`
- [x] `src/self_telemetry.py`
- [x] `src/signoz_mcp_adapter.py`
- [x] `src/telemetry_gateway.py`
- [x] `src/diagnosis_agent.py`
- [x] `src/orchestrator.py`
- [x] `src/run_patchnoz.py`
- [x] `src/run_recorder.py`
- [x] `runs/demo-checkout-payment/root_cause.json` generated (verified:
      root cause = `payment`, confidence 85%, real SigNoz trace links)

**Status: 9/9 complete.**

## Milestone 2 — Actions

- [x] `src/action_agent.py`
- [x] Slack dry-run output (verified in `runs/demo-checkout-payment/actions.json`)
- [x] Slack webhook integration (verified live: real `SLACK_WEBHOOK_URL` set,
      `status: "success"`, message confirmed received in Slack)
- [x] GitHub issue dry-run (verified in `runs/demo-checkout-payment/actions.json`)
- [x] GitHub issue creation (verified live: real issue created at
      https://github.com/thisisvaishnav/PatchNoz/issues/5 — first attempt hit
      a `403 Resource not accessible by personal access token` error, fixed
      by improving `src/adapters/github.py` to surface GitHub's actual error
      body, then by widening the PAT's Issues: write permission for the repo)
- [x] `runs/demo-checkout-payment/actions.json` generated

**Status: 6/6 complete.** ✅ Both Slack and GitHub actions have been
exercised end-to-end against real credentials, not just dry-run.

## Milestone 3 — Observing the Observer

- [x] Span: `patchnoz.incident.run` (confirmed present via direct SigNoz query)
- [x] Span: `patchnoz.telemetry.collect_evidence` (confirmed present)
- [x] Span: `patchnoz.signoz_mcp.call` (confirmed present, one per MCP tool call)
- [x] Span: `patchnoz.diagnosis.summarize` (confirmed present)
- [x] Span: `patchnoz.action.execute` (confirmed present, plus
      `patchnoz.action.slack` / `patchnoz.action.github` children)
- [x] Screenshot captured from SigNoz UI (SigNoz Services → `patchnoz-agent`
      → Key Operations, showing `patchnoz.incident.run` with real latency
      data: P50/P95/P99 = 722.08ms, 1 call, 0.00% error rate)

**Status: 6/6 complete.** ✅ Spans confirmed live via both the SigNoz API and
a screenshot of the SigNoz UI itself.

> Save the screenshot into `docs/screenshots/` (e.g.
> `docs/screenshots/signoz-patchnoz-agent.png`) so it can be embedded in the
> README/SUBMISSION.md — see "Still needed from you" under Milestone 4 below.

## Milestone 4 — Submission

- [x] README written (`README.md`: pitch, architecture, setup, env vars, run
      instructions, verification steps, repo layout)
- [x] Architecture diagram added (Mermaid diagram in `README.md`, renders in
      GitHub/Zed)
- [ ] Demo screenshots added
- [ ] Demo video recorded
- [ ] Submission text prepared (draft in `SUBMISSION.md`)

**Status: 2/5 complete.**

### Still needed from you

1. Save the SigNoz screenshot (Services → `patchnoz-agent` → Key Operations)
   into `docs/screenshots/signoz-patchnoz-agent.png` so it can be embedded
   directly in `README.md` and `SUBMISSION.md`.
2. Record a short demo video (screen capture of the CLI run + the SigNoz UI
   showing the resulting spans/traces).
3. Finalize `SUBMISSION.md` with your team name, repo URL, and links to the
   video/screenshots, then paste into your hackathon platform's submission
   form.

---

## Implementation Log

### Day 1 — Deep Demo Spine (Completed ✅)

**Goal:** `simulated alert → evidence → root_cause.json → self-traces in SigNoz`

- `src/models.py`, `src/self_telemetry.py`, `src/signoz_mcp_adapter.py`,
  `src/telemetry_gateway.py`, `src/diagnosis_agent.py`, `src/orchestrator.py`,
  `src/run_recorder.py`, `src/run_patchnoz.py`.
- Verified: `python src/run_patchnoz.py --scenario checkout-payment-latency`
  runs end-to-end and produces `runs/demo-checkout-payment/*.json`.

### Day 2 — Diagnose → Act, Hardened Adapter (Completed ✅)

**Goal:** `RootCauseSummary → real/dry-run remediation actions`, plus a
correctness pass on the models, telemetry, and adapter layers.

#### What changed

- **`src/models.py`** — Re-shaped `IncidentAlert` (`condition`, `time_range`,
  `suspected_area`), `EvidenceItem` (`source`, `service`, `summary`, `raw`, `url`),
  `IncidentEvidence` (`items`), `RootCauseSummary` (`confidence`, `sig_noz_links`),
  `ActionResult` (`name`, `status`, `url`, `details`), `IncidentRun`
  (`alert`, `evidence`, `root_cause`, `actions`, plus lifecycle bookkeeping).
- **`src/self_telemetry.py`** — `configure_tracing()` / `get_tracer()` public API,
  plus a `start_span()` helper used by every module. Standard span names:
  `patchnoz.incident.run`, `patchnoz.telemetry.collect_evidence`,
  `patchnoz.signoz_mcp.call`, `patchnoz.diagnosis.summarize`,
  `patchnoz.action.execute`, `patchnoz.action.slack`, `patchnoz.action.github`.
- **`src/signoz_mcp_adapter.py`** — Simplified to `call_tool()` +
  `list_services()` / `search_traces()` / `search_logs()` / `list_alerts()`.
  Removed hardcoded credentials; login is attempted only when
  `SIGNOZ_EMAIL`/`SIGNOZ_PASSWORD`/`SIGNOZ_ORG_ID` (or `SIGNOZ_API_KEY`) are set,
  otherwise it raises a clear configuration error. Every call is wrapped in a
  `patchnoz.signoz_mcp.call` span.
- **`src/telemetry_gateway.py`** — `collect_evidence(alert)` normalizes raw MCP
  responses into `EvidenceItem`s and stays resilient: a failing tool call
  produces one `source="error"` evidence item instead of aborting the run.
  Includes SigNoz deep links (`/services/<service>`, `/trace/<trace_id>`).
- **`src/diagnosis_agent.py`** — Deterministic root-cause heuristic tuned for
  checkout-payment-latency (confidence 0.7–0.85 when payment/charge evidence
  is present), with a generic fallback for other services.
- **`src/action_agent.py` + `src/adapters/{slack,github}.py`** (**new**) —
  `ActionAgent.execute(summary)` posts a Slack incident summary and opens a
  GitHub issue with the suggested fix. Both dry-run automatically when
  `SLACK_WEBHOOK_URL` / `GITHUB_TOKEN`+`GITHUB_OWNER`+`GITHUB_REPO` aren't set,
  so the pipeline is always runnable without extra setup. GitHub PR creation
  and SigNoz dashboard creation remain explicit stretch goals, not required
  for the MVP.
- **`src/run_recorder.py`** — Reworked around `runs/<incident_id>/` with
  `save_alert` / `save_evidence` / `save_root_cause` / `save_actions` /
  `save_progress`.
- **`src/orchestrator.py`** — `IncidentOrchestrator.run(alert)` now drives the
  full pipeline including `ActionAgent`, records `actions.json`, and always
  writes `progress.md` (even on failure) inside one `patchnoz.incident.run` span.
- **`src/mcp_server.py`** — Left demoted/unwired as instructed; annotated with
  a docstring explaining it predates the `TelemetryGateway` refactor and is
  not part of the current pipeline. PatchNoz consumes SigNoz's MCP server;
  it does not ship a competing one.

#### Verification & Definition of Done

1. **CLI execution**: `python src/run_patchnoz.py --scenario checkout-payment-latency`
   runs end-to-end without crashing, with or without SigNoz credentials set.
2. **Evidence collection**: With `SIGNOZ_EMAIL`/`SIGNOZ_PASSWORD`/`SIGNOZ_ORG_ID`
   set, evidence includes live service metrics, trace rows, and log rows from
   SigNoz, with working `/services/...` and `/trace/...` deep links.
3. **Diagnosis**: Root cause correctly attributes checkout latency to the
   `payment` service with ~85% confidence when payment/charge evidence is present.
4. **Actions**: `ActionAgent` always returns a `slack` and a `github` action;
   both dry-run cleanly with no credentials configured, and the dry-run
   payload (message/issue body) is saved in `actions.json` for inspection.
5. **Artifacts**: `runs/demo-checkout-payment/{alert,evidence,root_cause,actions}.json`
   and `progress.md` are all produced on every run.
6. **Self-observability**: `patchnoz-agent` spans (`patchnoz.incident.run`,
   `patchnoz.telemetry.collect_evidence`, `patchnoz.signoz_mcp.call`,
   `patchnoz.diagnosis.summarize`, `patchnoz.action.execute`,
   `patchnoz.action.slack`, `patchnoz.action.github`) are visible in the
   SigNoz UI at `http://localhost:8080`.

### Day 2.1 — `.env` support (Completed ✅)

- **`src/env.py`** (new) — Loads a repo-root `.env` file via `python-dotenv`
  exactly once, without overriding variables already set in the shell.
  Imported (and called) at the top of `signoz_mcp_adapter.py`,
  `adapters/slack.py`, `adapters/github.py`, and `self_telemetry.py`, since
  those modules read their configuration as module-level constants at
  import time.
- **`.env.example`** (new) — Documents every PatchNoz env var; copy to
  `.env` and fill in what you have. `.env` was already covered by
  `.gitignore`.
- Verified: `python src/run_patchnoz.py --scenario checkout-payment-latency`
  picks up SigNoz credentials from `.env` with nothing exported in the shell.

### Day 3 — Live SigNoz + OTel Demo verification (Completed ✅)

**Goal:** Confirm the pipeline against a real running SigNoz + OpenTelemetry
Demo stack, not just the graceful-failure path.

- Confirmed `http://localhost:8080` (`200 OK`), `http://localhost:8000/mcp`
  (authenticated adapter calls succeed), and OTLP `:4317` all reachable.
- Re-ran `python src/run_patchnoz.py --scenario checkout-payment-latency`;
  no exporter connection errors, real evidence collected (real trace IDs,
  `db.statement`, `k8s.pod.name`, payment `transactionId`/`cardType`/`amount`
  log fields from the OTel Demo).
- Queried SigNoz directly via `SigNozMCPAdapter.list_services()` and
  confirmed `patchnoz-agent` is registered as a live service.
- Queried `search_traces('patchnoz-agent')` and confirmed all 7 expected
  span names are present: `patchnoz.incident.run`,
  `patchnoz.telemetry.collect_evidence`, `patchnoz.signoz_mcp.call`,
  `patchnoz.diagnosis.summarize`, `patchnoz.action.execute`,
  `patchnoz.action.slack`, `patchnoz.action.github`.

### Day 4 — Live Slack + GitHub verification (Completed ✅)

**Goal:** Flip Milestone 2's two dry-run-only items to fully verified by
testing against real credentials.

- Set real `SLACK_WEBHOOK_URL`, `GITHUB_OWNER`, `GITHUB_REPO`, and
  `GITHUB_TOKEN` in `.env`.
- First GitHub attempt failed with a bare `HTTP Error 403: Forbidden`.
  Improved `src/adapters/github.py` to read and surface the actual GitHub
  API error body on `HTTPError` instead of just the status line, which
  revealed the real cause: `"Resource not accessible by personal access
  token"` — a token permissions issue, not a code bug.
- After widening the PAT's `Issues: write` permission for the target repo,
  re-ran the pipeline: both actions returned `status: "success"`.
  - Slack: message confirmed received in the target Slack channel.
  - GitHub: real issue created at
    https://github.com/thisisvaishnav/PatchNoz/issues/5 with the correct
    title, root cause, recommended fix, confidence, and SigNoz trace links.
- Captured a SigNoz UI screenshot (Services → `patchnoz-agent` → Key
  Operations) showing `patchnoz.incident.run` with real latency data,
  closing out Milestone 3.

## Next steps (not done yet)

1. Wire a real SigNoz alert webhook into `IncidentAlert.from_dict` instead of
   only simulating alerts via `--scenario`.
2. Optional: GitHub PR with an actual suggested code/config diff (stretch).
3. Optional: SigNoz dashboard/annotation creation for the incident (stretch).
4. Optional: swap `DiagnosisAgent`'s rule-based heuristic for an LLM call,
   keeping the same `RootCauseSummary` contract.
5. Save the SigNoz screenshot into `docs/screenshots/` and embed it in
   `README.md`/`SUBMISSION.md`.
6. Record demo video and finalize submission text (Milestone 4).
