# Replace rule-based TelemetryGateway and DiagnosisAgent with an LLM investigation agent

The original pipeline collected evidence in a fixed sequence
(`list_services` → `search_traces` → `search_logs`) and diagnosed root cause with
hardcoded if/else rules tuned only to the checkout-payment scenario. This made the
system unable to handle any alert outside that one scenario and produced generic,
templated output regardless of what the evidence actually showed — the same canned
sentence appeared in Slack whether or not the real data supported it.

We replaced `TelemetryGateway` and `DiagnosisAgent` with a single LLM agent
(Gemini 2.5 Flash) that decides which SigNoz MCP tools to call based on what it
finds, iterates until it has enough evidence, and produces a structured JSON
diagnosis grounded in real observed values — specific error messages, actual p99
numbers, affected user patterns, and a reasoning trace for the confidence score.
The agent works for any service and any alert type without pre-written rules.

## Considered options

**More rules** — extend `DiagnosisAgent` to cover more alert scenarios. Rejected:
every new scenario requires code; the space of possible incidents is unbounded.

**Hybrid (rules for collection, LLM for writing)** — keep the pre-planned evidence
collection sequence, use the LLM only to write the Slack/GitHub message. Rejected:
the pre-planned sequence is itself the limitation. The LLM needs to decide *what*
to query, not just how to describe what was already collected.

## Consequences

- Each Investigation costs API tokens (~70k input + 3k output on Gemini 2.5 Flash,
  ~$0.028 per incident at paid rates). Mitigated by Gemini's free tier
  (~1,500 requests/day), which covers this project at any realistic alert volume.
- Investigation output is non-deterministic. The same alert may produce slightly
  different diagnoses across runs. Acceptable: the goal is developer-quality
  reasoning, not byte-identical reproducibility.
- The rule-based fallback path is removed. If the LLM API is unavailable, the
  Investigation fails with a clear error rather than producing a confidently wrong
  answer. This is the correct behaviour.
