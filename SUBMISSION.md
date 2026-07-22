# PatchNoz — Submission Draft

> This is a draft write-up. Copy/paste the sections you need into whatever
> hackathon submission platform you're using (Devpost, etc.), trimming to
> fit any character limits. Fill in the bracketed placeholders before
> submitting.

## Tagline

AutoSRE-lite: an agent that diagnoses SigNoz incidents and traces its own
reasoning back into SigNoz.

## Elevator pitch (2–3 sentences)

PatchNoz turns a SigNoz alert into a diagnosed root cause and a drafted fix
in seconds. It queries SigNoz's own telemetry (traces, logs, metrics) through
SigNoz's prebuilt MCP server, reasons about the likely root cause, drafts a
Slack summary and a GitHub issue, and — critically — traces its *own*
AI/tool pipeline back into SigNoz with OpenTelemetry, so you can watch the
agent's reasoning as spans right next to the telemetry it's investigating.

## The problem

On-call engineers spend the first 10–20 minutes of any incident just
gathering context: which service is slow, which trace is the outlier, what
do the logs say. That triage work is repetitive, mechanical, and a great fit
for automation — but most "AI SRE" demos either hardcode fake data or become
a black box you can't audit. If you can't observe your AI agent, you don't
really own it.

## What it does

1. Receives (or simulates) a SigNoz alert, e.g. "Checkout latency spike."
2. `TelemetryGateway` calls SigNoz's own prebuilt MCP server to pull real
   service metrics, trace rows, and log rows for the affected service and
   its suspected dependency.
3. `DiagnosisAgent` turns that evidence into a `RootCauseSummary`: suspected
   root-cause service, plain-English explanation, recommended fix, and a
   confidence score.
4. `ActionAgent` drafts a Slack incident summary and opens a GitHub issue
   with the suggested fix — both dry-run safely if no webhook/token is
   configured, so the demo always works.
5. Every step is wrapped in an OpenTelemetry span and exported back to
   SigNoz under the service name `patchnoz-agent`, so the agent's own
   `incident.run → collect_evidence → signoz_mcp.call → diagnosis.summarize →
   action.execute` pipeline shows up as a trace next to the checkout/payment
   telemetry it diagnosed.
6. Every artifact (`alert.json`, `evidence.json`, `root_cause.json`,
   `actions.json`, `progress.md`) is saved to `runs/<incident_id>/` for
   inspection and demo replay.

## How we built it

- Python 3.11+, standard library where possible (`urllib.request` for
  Slack/GitHub HTTP calls — no extra HTTP client dependency).
- OpenTelemetry Python SDK, exporting via OTLP gRPC to a locally running
  SigNoz instance.
- SigNoz's **prebuilt MCP server** as the sole telemetry source — we
  deliberately did not build a competing custom MCP server. PatchNoz is an
  agent orchestration app, not another observability backend.
- The OpenTelemetry Demo (`checkout` → `payment` flow) as the source of
  realistic, multi-service telemetry to diagnose against.
- A small adapter/gateway layering (`SigNozMCPAdapter` → `TelemetryGateway`)
  so all SigNoz-specific JSON-RPC/HTTP details are isolated behind a clean
  `collect_evidence(alert) -> IncidentEvidence` interface.

## Challenges we ran into

- Making the pipeline resilient to a *partially* available SigNoz: if one
  MCP tool call fails (e.g. `search_logs` for a service with no logs), the
  run should still produce a usable `root_cause.json` instead of crashing —
  solved by capturing failures as `source: "error"` evidence items instead
  of raising.
- Keeping credentials out of the codebase entirely while still supporting a
  zero-config demo path: every external integration (SigNoz auth, Slack,
  GitHub) reads from environment variables (with `.env` support) and
  degrades to a dry-run/clear-error mode when unset.
- Avoiding the trap of building "yet another MCP server" — the natural
  instinct when integrating with MCP is to expose your own tools. We
  explicitly kept PatchNoz as a pure MCP *client* of SigNoz's server.

## Accomplishments we're proud of

- The full pipeline — simulated alert → real SigNoz evidence → root cause →
  live remediation → saved artifacts — runs end-to-end with a single
  command: `python src/run_patchnoz.py --scenario checkout-payment-latency`.
- Verified live: `patchnoz-agent` shows up as a first-class service in
  SigNoz, and all 7 pipeline spans (`patchnoz.incident.run` through
  `patchnoz.action.github`) are queryable directly from SigNoz's API *and*
  visible in the SigNoz UI — the self-observability claim isn't just
  asserted, it's been checked against a live SigNoz instance.
- Both remediation actions were exercised for real, not just dry-run: a
  live Slack message was posted, and a live GitHub issue was opened at
  https://github.com/thisisvaishnav/PatchNoz/issues/5 with the diagnosed
  root cause, recommended fix, and SigNoz trace links.
- Zero hardcoded secrets anywhere in the codebase — every credential is
  read from the environment / `.env`, and the GitHub adapter surfaces the
  real API error body (not just a generic status code) to make
  credential/permission issues self-diagnosing.

## What's next

- Wire a real SigNoz alert **webhook** as an alternate entry point, instead
  of only the `--scenario` simulated alert.
- Swap the rule-based `DiagnosisAgent` for an LLM call behind the same
  `RootCauseSummary` contract, once the deterministic pipeline is fully
  trusted.
- GitHub PR creation with an actual suggested code/config diff, and a SigNoz
  dashboard/annotation for the incident (both scoped as stretch goals from
  day one).

## Built with

Python, OpenTelemetry, SigNoz, SigNoz MCP server, OpenTelemetry Demo, Slack
Incoming Webhooks, GitHub REST API.

## Try it out

```bash
git clone [repo URL]
cd PatchNoz
source venv/bin/activate   # or set up your own venv per README.md
cp .env.example .env       # optional: fill in SigNoz/Slack/GitHub credentials
python src/run_patchnoz.py --scenario checkout-payment-latency
```

See [`README.md`](./README.md) for full setup instructions and
[`PROJECT_PROGRESS.md`](./PROJECT_PROGRESS.md) for the detailed build log.

---

## Placeholders to fill in before submitting

- [ ] `[repo URL]` above
- [ ] Team name / member names
- [ ] Link(s) to demo video
- [ ] Link(s) to screenshots (or embed them directly in this file)
- [ ] Hackathon-specific category/track, if applicable
- [ ] Any character-limit trims required by the submission platform
