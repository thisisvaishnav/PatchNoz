# PatchNoz

An autonomous SRE agent that monitors SigNoz for firing alerts, investigates each
alert by querying SigNoz telemetry through its MCP server, and produces a
developer-quality incident diagnosis — posted to Slack and filed as a GitHub issue.

## Language

### Triggering

**Alert**:
A currently-firing SigNoz alert — the unit of work that triggers an Investigation.
PatchNoz does not detect anomalies itself; it acts on alerts SigNoz has already
decided are worth acting on.
_Avoid_: Incident (overloaded), anomaly, event

**Scan cycle**:
A periodic sweep that calls `signoz_list_alerts`, deduplicates against open GitHub
issues, and initiates one Investigation per new firing Alert.
_Avoid_: Polling, monitoring loop, sweep

### Investigation

**Investigation**:
A single LLM agent run initiated for one Alert. The agent calls SigNoz MCP tools
iteratively — deciding what to query based on what it finds — and terminates when
it produces an InvestigationResult.
_Avoid_: Diagnosis (the deleted rule-based predecessor), analysis

**Tool call**:
A single call from the LLM agent to a SigNoz MCP tool (`list_services`,
`search_traces`, `search_logs`, `list_alerts`) during an Investigation. The agent
makes tool calls until it has enough evidence to produce an InvestigationResult.
_Avoid_: Query, request, API call

**InvestigationResult**:
The structured JSON output produced at the end of an Investigation. Contains the
root cause service, specific error messages observed in traces and logs, affected
user patterns, confidence reasoning (not just a percentage), recommended fix steps,
and pre-rendered content for Slack and GitHub.
_Avoid_: RootCauseSummary (the deleted predecessor), report, diagnosis

### Actions

**Action**:
A downstream artifact created from an InvestigationResult — either a Slack post or
a GitHub issue. One Investigation produces exactly two Actions.
_Avoid_: Notification, output, remediation

**Deduplication**:
The GitHub search performed before opening an issue to check whether an open issue
already exists for the same service and alert name. Prevents a new issue being
opened on every Scan cycle for an ongoing Alert.
_Avoid_: Idempotency check, duplicate guard
