# AGENT.md — PatchNoz

Guidance for AI coding agents (and humans) working in this repository.
PatchNoz is an **AutoSRE-lite agent on top of SigNoz**: it receives/simulates
a SigNoz alert, gathers evidence through SigNoz's prebuilt MCP server,
diagnoses a root cause, drafts Slack/GitHub remediation actions, and traces
its own execution back into SigNoz with OpenTelemetry.

---

## 1. Technology Stack

### Language & runtime
- **Python 3.11+** (local `venv` currently on 3.14). Standard library
  dataclasses only for domain models — no ORM, no web framework.

### Package manager
- **pip**, installed directly into the project's `venv/` (gitignored).
- There is **no `requirements.txt` / `pyproject.toml` yet** — if you add a
  new dependency, install it into `venv` and also add it to a
  `requirements.txt` (create one if it doesn't exist) so the environment is
  reproducible.

### Key libraries (installed in `venv`)
| Package | Purpose |
|---|---|
| `opentelemetry-api` / `-sdk` / `-exporter-otlp-proto-grpc` | Self-telemetry: traces PatchNoz's own pipeline into SigNoz |
| `mcp` | Model Context Protocol client/server primitives |
| `python-dotenv` | Loads `.env` once at import time (see `src/env.py`) |
| `httpx`, `urllib` (stdlib) | HTTP calls to SigNoz API/MCP, Slack, GitHub |
| `pydantic` / `pydantic-settings` | Used transitively by `mcp` |
| `starlette` / `uvicorn` / `sse-starlette` | Transitive, used by the (demoted) `src/mcp_server.py` FastMCP server |

### Datastores / backends (external, not part of this repo)
- **SigNoz** (self-hosted via Docker Compose) — UI/API on `:8080`, OTLP gRPC
  ingest on `:4317` (HTTP `:4318`), prebuilt MCP server on `:8000/mcp`.
- Backing SigNoz itself: ClickHouse (telemetry store) + Postgres (metastore).
  PatchNoz never talks to these directly — always through SigNoz's HTTP API
  or its MCP server.

### External services (optional, dry-run if unset)
- **Slack** — Incoming Webhook (`SLACK_WEBHOOK_URL`).
- **GitHub** — REST API for issue creation (`GITHUB_TOKEN`, `GITHUB_OWNER`,
  `GITHUB_REPO`).

---

## 2. Architecture Highlights

### Pipeline (single incident, synchronous)
```
run_patchnoz.py (CLI)
  -> IncidentOrchestrator.run(alert)
       -> TelemetryGateway.collect_evidence(alert)
            -> SigNozMCPAdapter -> SigNoz prebuilt MCP server (:8000/mcp)
       -> DiagnosisAgent.diagnose(alert, evidence) -> RootCauseSummary
       -> ActionAgent.execute(root_cause) -> Slack + GitHub ActionResults
       -> RunRecorder -> runs/<incident_id>/{alert,evidence,root_cause,actions}.json, progress.md
       -> self_telemetry -> OTLP :4317 -> SigNoz (patchnoz-agent spans)
```

### Key folders / files
| Path | Role |
|---|---|
| `src/run_patchnoz.py` | CLI entry point (`--scenario <name>`) |
| `src/orchestrator.py` | `IncidentOrchestrator` — owns pipeline ordering + failure handling, one root span |
| `src/models.py` | Plain dataclasses: `IncidentAlert`, `EvidenceItem`, `IncidentEvidence`, `RootCauseSummary`, `ActionResult`, `IncidentRun` |
| `src/telemetry_gateway.py` | Normalizes raw SigNoz MCP responses into `EvidenceItem`s; resilient to per-tool failures |
| `src/signoz_mcp_adapter.py` | **Only** place that knows SigNoz's native MCP tool names, JSON-RPC envelope, and auth flow |
| `src/diagnosis_agent.py` | Evidence → `RootCauseSummary` (deterministic, rule-based heuristic) |
| `src/action_agent.py` | `RootCauseSummary` → `ActionResult[]` (Slack + GitHub) |
| `src/adapters/slack.py` | Slack Incoming Webhook client, dry-runs without `SLACK_WEBHOOK_URL` |
| `src/adapters/github.py` | GitHub issue creation, dry-runs without token/owner/repo |
| `src/adapters/dashboard.py` | Stretch goal, **not implemented** |
| `src/self_telemetry.py` | OTel setup: `configure_tracing()`, `get_tracer()`, `start_span()` helper used by every module |
| `src/run_recorder.py` | Persists `runs/<incident_id>/*.json` + `progress.md` |
| `src/env.py` | Loads repo-root `.env` exactly once via `python-dotenv`, without overriding shell vars |
| `src/mcp_client.py` | Backward-compat re-export of `SigNozMCPAdapter` |
| `src/mcp_server.py` | **DEMOTED** — predates current architecture, not wired into the pipeline. Do not extend; PatchNoz is a *client* of SigNoz's MCP server, not a competing one |
| `scripts/` | Standalone smoke-test scripts (OTLP send, direct JSON-RPC, MCP client, telemetry gateway) — not a pytest suite |
| `runs/` | Output artifacts per incident, one directory per `incident_id` |

### Standard OTel span names (self-observability contract)
`patchnoz.cli.run` → `patchnoz.incident.run` → `patchnoz.telemetry.collect_evidence`
→ `patchnoz.signoz_mcp.call` (one per SigNoz tool call) → `patchnoz.diagnosis.summarize`
→ `patchnoz.action.execute` → `patchnoz.action.slack` / `patchnoz.action.github`.
Keep these names stable — dashboards/screens in the demo filter on them.

### "API" surface
There are no HTTP endpoints exposed by this repo. The only "API" boundaries are:
- **SigNoz MCP server** (`:8000/mcp`, JSON-RPC over HTTP) — consumed, not served, via `SigNozMCPAdapter`.
- **SigNoz REST API** (`:8080/api/v2/...`) — used only for login (`/api/v2/sessions/email_password`).
- **Slack Incoming Webhook** and **GitHub REST API** — outbound only, via the adapters.

---

## 3. Build / Run / Test Commands

```bash
# Activate the project venv (from repo root: PatchNoz/)
source venv/bin/activate

# Run the full incident pipeline (default scenario: checkout-payment-latency)
python src/run_patchnoz.py --scenario checkout-payment-latency

# OTLP smoke test — sends one span named "test-manual" to SigNoz
python scripts/send_test_trace.py

# Direct JSON-RPC smoke test against SigNoz's MCP server
python scripts/test_direct_jsonrpc.py

# Exercise the demoted src/mcp_server.py tools directly
python scripts/test_mcp_client.py

# TelemetryGateway + DiagnosisAgent smoke test (evidence -> RootCauseSummary JSON)
python scripts/test_telemetry_gateway.py
```

There is **no formal test framework** (no pytest/unittest suite) — the
`scripts/*.py` files are manual smoke tests that print output and `assert`
inline. If you add real tests, prefer `pytest` and put them under a new
`tests/` directory rather than mixing them into `scripts/`.

### Prerequisites for a full run
- SigNoz stack running locally via `docker compose` (UI `:8080`, OTLP gRPC
  `:4317`, MCP server `:8000/mcp`).
- `.env` populated from `.env.example` (see below) — optional; the pipeline
  runs end-to-end even with nothing configured (see Guidelines).

### Environment variables (`.env`, loaded automatically via `src/env.py`)
| Variable | Purpose |
|---|---|
| `SIGNOZ_BASE_URL` | SigNoz UI/API base URL (default `http://localhost:8080`) |
| `SIGNOZ_MCP_URL` | SigNoz MCP server URL (default `http://localhost:8000/mcp`) |
| `SIGNOZ_API_KEY` | Preferred SigNoz auth |
| `SIGNOZ_EMAIL` / `SIGNOZ_PASSWORD` / `SIGNOZ_ORG_ID` | Fallback SigNoz login if no API key |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Where PatchNoz sends its own spans (default `http://localhost:4317`) |
| `SLACK_WEBHOOK_URL` | Enables a real Slack post |
| `GITHUB_TOKEN` / `GITHUB_OWNER` / `GITHUB_REPO` | Enables a real GitHub issue |

---

## 4. Guidelines

### Do
- **Do** keep `SigNozMCPAdapter` (`src/signoz_mcp_adapter.py`) as the single
  place that knows SigNoz's native MCP tool names and JSON-RPC envelope.
  Every other module should call it through `TelemetryGateway`, never raw HTTP.
- **Do** wrap every externally-observable unit of work in a
  `start_span(...)` from `src/self_telemetry.py`, using the existing
  `patchnoz.*` span naming convention.
- **Do** keep the pipeline resilient: a failing SigNoz/Slack/GitHub call
  should degrade to an `error`/`dry_run` result, not crash the whole run
  (see `TelemetryGateway.collect_evidence` and the adapters for the pattern).
- **Do** load configuration through `src/env.py` (`load_env()`) plus
  `os.getenv(...)` with a sane default — follow the existing module-level
  constant pattern in `signoz_mcp_adapter.py` / `adapters/slack.py` / `adapters/github.py`.
- **Do** persist any new artifact type through `RunRecorder`
  (`src/run_recorder.py`) under `runs/<incident_id>/`, and append a line to
  `progress.md` for anything user-visible.
- **Do** update `branches.md` on every new commit/branch, following the
  `<type>/<short-kebab-description>` convention already documented there.
- **Do** keep domain objects as plain dataclasses in `src/models.py` with
  `to_dict()`/`from_dict()` — this is the contract used for JSON handoffs
  between agents and for `runs/*.json` artifacts.
- **Do** prefer extending `DiagnosisAgent`/`ActionAgent` behind their
  existing method signatures (`diagnose(alert, evidence)` /
  `execute(root_cause)`) so the orchestrator never needs to change.

### Don't
- **Never** hardcode secrets, API keys, tokens, or webhook URLs anywhere in
  the repo. All credentials come from environment variables / `.env`
  (gitignored). If a credential is missing, fail closed into a `dry_run` or
  clear configuration error — don't silently no-op or use a fallback secret.
- **Don't** re-introduce or wire up `src/mcp_server.py` into the live
  pipeline — it's intentionally demoted. PatchNoz is a *client* of SigNoz's
  MCP server, not a second MCP server.
- **Don't** call SigNoz, Slack, or GitHub APIs directly from
  `orchestrator.py`, `diagnosis_agent.py`, or `run_patchnoz.py` — always go
  through the relevant adapter (`SigNozMCPAdapter`, `adapters/slack.py`,
  `adapters/github.py`).
- **Don't** rename or remove the standard `patchnoz.*` span names without
  updating every reference — the SigNoz demo view depends on them.
- **Don't** let one failed evidence source (metrics/traces/logs) abort the
  whole run — always degrade to a `source="error"` `EvidenceItem` instead.
- **Don't** commit anything under `runs/` that contains real
  customer/production data — treat `runs/` as demo/debug output only.
- **Don't** add a new dependency without also making it discoverable (update
  a `requirements.txt` if you create one, or at least note it in
  `PROJECT_PROGRESS.md`) — there's currently no lockfile to fall back on.
