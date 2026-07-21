# PatchNoz (PatchPilot / AutoSRE-lite)

## 1. What This Project Does

PatchNoz is an **AI-powered SRE teammate** that:

1. Receives an alert from SigNoz.
2. **Diagnoses** the root cause by querying traces, logs, and metrics via MCP tools.
3. **Acts** by:
   - Creating/updating a SigNoz dashboard with the relevant evidence.
   - Posting a structured summary to Slack.
   - **Opening a GitHub PR** with a suggested fix.
4. **Self-observes** – every agent call is traced with OpenTelemetry and sent back into SigNoz, so you can watch the agents themselves running.

> Hackathon tagline: *“If you can't observe your AI agents, you don't own them.”*

---

## 2. Tech Stack & Key Integrations

| Layer | Technology | Local status / notes |
|-------|------------|----------------------|
| **Observability backend** | SigNoz (self-hosted Docker Compose) | Running as Docker project `signoz` |
| **UI / API** | `signoz/signoz` | **http://localhost:8080** · health: `GET /api/v1/health` → `{"status":"ok"}` |
| **OTLP ingest** | `signoz/signoz-otel-collector` (ingester) | **gRPC `localhost:4317`**, HTTP `localhost:4318` |
| **Telemetry store** | ClickHouse + ClickHouse Keeper | Internal only (`9000` / keeper ports not published) |
| **Metastore** | Postgres 16 | Internal; DB `signoz` / user `signoz` |
| **MCP server** | `signoz/signoz-mcp-server` | **http://localhost:8000** · livez returns 200 |
| **Agent runtime (planned)** | Python + LangChain / custom agent loop + MCP | Repo uses Python `venv` |
| **LLM (planned)** | OpenAI-compatible API | Not wired yet |
| **Notification (planned)** | Slack Incoming Webhook | Not wired yet |
| **Version control (planned)** | GitHub API (PAT) | Not wired yet |
| **Meta-tracing** | OpenTelemetry Python SDK → OTLP → SigNoz | Verified with test script |
| **Infra (dev)** | Docker Compose, Python 3.11+ (local venv is 3.14) | — |

### Python packages (verified)

Installed in project `venv` for the smoke test:

- `opentelemetry-api`
- `opentelemetry-sdk`
- `opentelemetry-exporter-otlp-proto-grpc`

---

## 3. Skills & Knowledge You Must Have

### Core Programming
- **Python** – async code, JSON, HTTP, basic CLI.
- **Environment variables & config** – `.env` files, secrets management.

### Observability
- Difference between **traces, spans, metrics, and logs**.
- **OpenTelemetry**: context propagation, exporters, batch span processors.
- Run SigNoz via Docker and use the UI at **`http://localhost:8080`** (this stack is **not** on the older `localhost:3301` default).
- Export traces with OTLP to **`localhost:4317`** (gRPC) or **`localhost:4318`** (HTTP).
- Query SigNoz APIs / MCP tools for traces, logs, and metrics.

### MCP (Model Context Protocol)
- MCP architecture: **client ↔ server**, tool definitions (JSON schemas).
- Build or consume MCP tools (this environment already runs SigNoz’s MCP server on port **8000**).
- Agents call MCP tools by name and consume structured results.

### AI Agent Design
- Tool-calling agents, multi-agent chaining with JSON handoffs, prompt engineering for parseable output over observability data.

### APIs & Automation
- **GitHub API** – `POST /repos/{owner}/{repo}/pulls`.
- **Slack Webhooks** – blocks/attachments.
- **SigNoz Dashboard API** – create/update dashboards via JSON payloads.

### Docker / Basic DevOps
- `docker compose` for the SigNoz stack.
- Know that config files mounted into containers must be **real files**, not empty directories (Docker will create directories if paths are missing, which breaks ClickHouse/ingester mounts).

---

## 4. Architecture

### High-level flow (target)

```
SigNoz Alert
    │
    ▼
┌──────────────────┐     MCP tools      ┌─────────────────────┐
│  PatchNoz Agent  │◄──────────────────►│  SigNoz MCP :8000   │
│  (diagnose/act)  │                    │  traces/logs/metrics│
└────────┬─────────┘                    └──────────▲──────────┘
         │                                         │
         │ OTel spans (self-observe)               │ stores data
         ▼                                         │
   OTLP :4317 ──► Ingester ──► ClickHouse ◄────────┘
         │
         ├──► Slack summary
         ├──► SigNoz dashboard update
         └──► GitHub PR with suggested fix
```

### Local SigNoz stack (verified running)

Compose project name: **`signoz`**  
Compose file (this machine): `openSlice/pours/deployment/compose.yaml`  
(also mirrored under `Github/pours/deployment/`)

| Container | Role | Host ports |
|-----------|------|------------|
| `signoz-signoz-0` | UI + API | **8080** |
| `signoz-ingester-1` | OTLP collector / ingester | **4317** (gRPC), **4318** (HTTP) |
| `signoz-mcp` | SigNoz MCP server | **8000** |
| `signoz-telemetrystore-clickhouse-0-0` | Trace/metrics/log store | (internal) |
| `signoz-telemetrykeeper-clickhousekeeper-0` | ClickHouse Keeper | (internal) |
| `signoz-metastore-postgres-0` | App metadata / SQL store | (internal) |

Network: Docker network **`signoz-network`**.

### Bring stack up / down

```bash
cd /path/to/pours/deployment   # compose.yaml location
docker compose up -d
docker compose ps
docker compose down            # stop when finished
```

Health checks that worked during setup:

```bash
curl http://localhost:8080/api/v1/health   # {"status":"ok"}
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/livez  # 200
nc -z localhost 4317 && echo 'OTLP gRPC up'
```

### Repo layout (current)

```
PatchNoz/
├── patchnoz.md                 # this doc (project overview)
├── branches.md                 # branch names chosen per commit (update every commit)
├── .gitignore                  # from branch chore/add-gitignore
├── src/
│   └── mcp_server.py           # Custom FastMCP server for SigNoz (traces, logs, metrics)
├── scripts/
│   ├── send_test_trace.py      # OTLP smoke test → localhost:4317
│   └── test_mcp_client.py      # Client test script for SigNoz MCP tools
└── venv/                       # Python env with OpenTelemetry & MCP packages (gitignored)
```

### Branch tracking

All branch names used for commits are logged in **[`branches.md`](./branches.md)**.

| Rule | Detail |
|------|--------|
| **When** | On **every new commit**, add a row to `branches.md` |
| **How named** | `<type>/<short-kebab-description>` (e.g. `chore/add-gitignore`) |
| **First branch** | `chore/add-gitignore` → commit `chore: add .gitignore file` (`d393999`) |

Do not invent ad-hoc branch names without recording them in `branches.md`.

---

## 5. Smoke test: send a trace into SigNoz

Script: **`scripts/send_test_trace.py`**

What it does:

1. Creates a `TracerProvider` + `BatchSpanProcessor`.
2. Exports via **OTLP gRPC** to `http://localhost:4317` (`insecure=True`).
3. Emits a single span named **`test-manual`**.
4. Sleeps 2s so the batch exporter can flush.

Run:

```bash
cd /Users/bombermac/Github/PatchNoz
source venv/bin/activate
python scripts/send_test_trace.py
# expected stdout: Trace sent.
```

Then open **http://localhost:8080** → **Traces** and look for span **`test-manual`**.

Core exporter snippet (what the script uses):

```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

trace.set_tracer_provider(TracerProvider())
span_exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(span_exporter))
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("test-manual"):
    print("Trace sent.")
```

---

## 6. SigNoz MCP Server (`src/mcp_server.py`)

Built using Python FastMCP (MCP SDK). It exposes tools to query traces, logs, and metric anomalies:

### Exposed Tools
- **`get_recent_traces(service_name, time_range, limit)`**: Fetches recent traces for a service, returning trace IDs, operation names, durations, error status, timestamps, and deep links.
- **`get_recent_logs(service_name, time_range, query, severity, limit)`**: Queries logs filtered by service, text query, and severity level.
- **`get_metric_anomalies(service_name, metric_name, time_range)`**: Evaluates error rate spikes (>1%), p99 latency spikes (>1s), call rates, and top bottleneck operations across services.

### Test Client & Verification (`scripts/test_mcp_client.py`)
Tests all 3 tools in-process and verifies stdio protocol initialization over JSON-RPC.

**Run test:**
```bash
python scripts/test_mcp_client.py
```

**Verification Results:**
- `get_recent_traces("frontend")`: Successfully fetched recent spans for the frontend service.
- `get_metric_anomalies("checkout")`: Detected high error rate (27.03%) and p99 latency spike (46.6s) on `oteldemo.CheckoutService/PlaceOrder` and `oteldemo.PaymentService/Charge`.
- **Stdio Protocol Test**: JSON-RPC initialize request returned a valid 200 response from FastMCP.

---

## 7. Ops notes from local setup

- **Wrong UI port in older docs:** classic SigNoz used `localhost:3301`. This deployment exposes the UI on **`8080`**.
- **OTLP must be up before agents can self-observe.** If `:4317` is closed, check that `signoz-ingester-1` and ClickHouse are running (`docker ps`).
- **Broken mounts:** if host paths like `config-0-0.yaml` or `ingester.yaml` are missing, Docker creates **directories** with those names. ClickHouse/ingester then fail with “not a directory” mount errors. Fix by replacing those directories with the real config **files** and `docker compose up -d` again.
- **MCP:** `signoz-mcp` may show `unhealthy` briefly during start; `GET /livez` returning **200** is the practical readiness signal.

---

## 8. Next build steps (not done yet)

1. Wire agent loop (alert webhook → diagnose → act).
2. Use SigNoz MCP tools on `:8000` or via custom MCP server (`src/mcp_server.py`) for traces/logs/metrics queries.
3. Slack + GitHub PR actions.
4. Instrument the agent itself with OTel (same OTLP path as the smoke test) so agent runs appear in SigNoz.
5. Optional: set `service.name` resource attributes so traces show as a clear service (e.g. `patchnoz-agent`) instead of a default/unknown name.

