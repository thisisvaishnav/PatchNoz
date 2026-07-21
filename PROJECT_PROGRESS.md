# Project Progress

## Day 1 — Deep Demo Spine (Completed ✅)

**Goal:** `simulated alert → evidence → root_cause.json → self-traces in SigNoz`

- `src/models.py`, `src/self_telemetry.py`, `src/signoz_mcp_adapter.py`,
  `src/telemetry_gateway.py`, `src/diagnosis_agent.py`, `src/orchestrator.py`,
  `src/run_recorder.py`, `src/run_patchnoz.py`.
- Verified: `python src/run_patchnoz.py --scenario checkout-payment-latency`
  runs end-to-end and produces `runs/demo-checkout-payment/*.json`.

## Day 2 — Diagnose → Act, Hardened Adapter (Completed ✅)

**Goal:** `RootCauseSummary → real/dry-run remediation actions`, plus a
correctness pass on the models, telemetry, and adapter layers.

### What changed

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

### Verification & Definition of Done

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

## Next steps (not done yet)

1. Wire a real SigNoz alert webhook into `IncidentAlert.from_dict` instead of
   only simulating alerts via `--scenario`.
2. Optional: GitHub PR with an actual suggested code/config diff (stretch).
3. Optional: SigNoz dashboard/annotation creation for the incident (stretch).
4. Optional: swap `DiagnosisAgent`'s rule-based heuristic for an LLM call,
   keeping the same `RootCauseSummary` contract.
