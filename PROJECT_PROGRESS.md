# Project Progress

## Day 1 — Build the Deep Demo Spine (Completed ✅)

**Goal:** `simulated alert → evidence → root_cause.json → self-traces in SigNoz`

### Implemented Modules
- `src/models.py`: Domain objects (`IncidentAlert`, `IncidentEvidence`, `RootCauseSummary`, `IncidentRun`, `ActionResult`).
- `src/self_telemetry.py`: OpenTelemetry exporter sending `patchnoz-agent` spans directly to SigNoz ingester on `localhost:4317`.
- `src/signoz_mcp_adapter.py`: Calls native SigNoz MCP tools (`signoz_list_services`, `signoz_search_traces`, `signoz_search_logs`, `signoz_get_service_top_operations`, `signoz_list_alerts`) via JSON-RPC over HTTP.
- `src/telemetry_gateway.py`: Decoupled domain-specific telemetry gatherer interface.
- `src/diagnosis_agent.py`: Synthesizes evidence into root-cause summaries and recommended fixes.
- `src/orchestrator.py`: `IncidentOrchestrator` driving the full end-to-end diagnosis pipeline with OTel tracing.
- `src/run_recorder.py`: Persists run artifacts (`alert.json`, `evidence.json`, `root_cause.json`, `progress.md`).
- `src/run_patchnoz.py`: CLI entry point (`--scenario checkout-payment-latency`).

### Verification & Definition of Done
1. **CLI Execution**: `python src/run_patchnoz.py --scenario checkout-payment-latency` executes end-to-end without crashing.
2. **Evidence Collection**: Queries live SigNoz metrics, traces, and logs.
3. **Artifact Generation**: Produces `runs/demo-checkout-payment/{alert.json, evidence.json, root_cause.json, progress.md}`.
4. **Self-Observability**: `patchnoz-agent` traces (`orchestrator.run`, `telemetry.collect_evidence`, `diagnosis.diagnose`, `recorder.save_artifacts`) visible in SigNoz UI.
