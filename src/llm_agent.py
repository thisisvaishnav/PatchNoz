"""
LLM Investigation Agent

A bare Gemini API loop that investigates a SigNoz Alert by calling SigNoz MCP
tools iteratively, then produces a structured InvestigationResult grounded in
real observed evidence -- not template sentences.

The agent has a budget of MAX_TOOL_CALLS tool invocations. It calls
signoz_list_services, signoz_search_traces, signoz_search_logs, and
signoz_list_alerts as many times as needed to find the root cause, then
signals completion by calling the special report_findings pseudo-tool.

Tool responses are pruned to diagnostic fields before being fed back to the
LLM, keeping token usage around 70k input per investigation.
"""

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from google import genai
from google.genai import types

from src.env import load_env
from src.models import IncidentAlert, InvestigationResult
from src.self_telemetry import start_span
from src.signoz_mcp_adapter import SIGNOZ_BASE_URL, SigNozMCPAdapter, default_adapter

load_env()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MAX_TOOL_CALLS = int(os.getenv("PATCHNOZ_MAX_TOOL_CALLS", "12"))

# ---------------------------------------------------------------------------
# Diagnostic field allowlists -- only these fields are forwarded to the LLM
# to keep token count low without losing evidence value.
# ---------------------------------------------------------------------------

_TRACE_KEEP = {
    "trace_id", "span_id", "name", "duration_nano", "has_error",
    "status_code", "status_code_string", "status_message",
    "http.request.method", "http.response.status_code", "http.route",
    "http_url", "http_method", "rpc.method", "rpc.service",
    "db.statement", "db.system", "db.operation",
    "service.name", "service.version",
    "kind_string", "timestamp", "webUrl",
}

_LOG_KEEP = {
    "body", "severity_text", "severity_number", "timestamp",
    "trace_id", "span_id",
}

_LOG_ATTRS_KEEP = {
    "error", "exception.message", "exception.type", "exception.stacktrace",
    "amount", "cardType", "loyalty_level", "transactionId",
    "http.status_code", "rpc.code",
}


def _prune_trace_row(row: Dict[str, Any]) -> Dict[str, Any]:
    data = row.get("data", row)
    pruned = {k: v for k, v in data.items() if k in _TRACE_KEEP and v not in ("", None, 0)}
    if "duration_nano" in pruned:
        pruned["duration_ms"] = round(pruned.pop("duration_nano") / 1e6, 2)
    return pruned


def _prune_log_row(row: Dict[str, Any]) -> Dict[str, Any]:
    data = row.get("data", row)
    pruned = {k: v for k, v in data.items() if k in _LOG_KEEP and v not in ("", None)}
    attrs = data.get("attributes_string", {})
    if attrs:
        pruned["attributes"] = {k: v for k, v in attrs.items() if k in _LOG_ATTRS_KEEP and v}
    return pruned


def _prune_service_row(row: Dict[str, Any]) -> Dict[str, Any]:
    keep = {"serviceName", "p99", "errorRate", "callRate", "numCalls", "numErrors", "webUrl"}
    pruned = {k: v for k, v in row.items() if k in keep}
    if "p99" in pruned:
        pruned["p99_ms"] = round(pruned.pop("p99") / 1e6, 2)
    return pruned


def _format_tool_response(tool_name: str, raw_result: Dict[str, Any]) -> str:
    """Prune and serialise a SigNoz MCP result to a compact JSON string."""
    try:
        if tool_name == "signoz_list_services":
            rows = _extract_rows(raw_result)
            pruned = [_prune_service_row(r) for r in rows]
            return json.dumps(pruned, default=str)

        elif tool_name == "signoz_search_traces":
            rows = _extract_rows(raw_result)
            pruned = [_prune_trace_row(r) for r in rows if r]
            return json.dumps(pruned, default=str)

        elif tool_name == "signoz_search_logs":
            rows = _extract_rows(raw_result)
            pruned = [_prune_log_row(r) for r in rows if r]
            return json.dumps(pruned, default=str)

        else:
            return json.dumps(raw_result, default=str)[:8000]

    except Exception as exc:
        return json.dumps({"error": f"Failed to format response: {exc}"})


def _extract_rows(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(result, dict):
        return []
    if isinstance(result.get("data"), list):
        return result["data"]
    nested = result.get("data", {}).get("data", {}).get("results", [])
    if nested and nested[0].get("rows"):
        return nested[0]["rows"]
    return []


# ---------------------------------------------------------------------------
# Tool / function declarations
# ---------------------------------------------------------------------------

_SIGNOZ_TOOLS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="signoz_list_services",
        description=(
            "Return current health metrics (p99 latency, error rate, call rate) "
            "for every service SigNoz knows about. Call this first to get a "
            "baseline picture of which services are unhealthy."
        ),
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="signoz_search_traces",
        description=(
            "Search recent traces for a specific service. Returns span-level data "
            "including operation name, duration, status code, status message, and "
            "HTTP/RPC attributes. Use to find slow or failing operations."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "service": types.Schema(
                    type=types.Type.STRING,
                    description="Exact service name as known to SigNoz.",
                ),
                "limit": types.Schema(
                    type=types.Type.INTEGER,
                    description="Max traces to return (default 5, max 20).",
                ),
            },
            required=["service"],
        ),
    ),
    types.FunctionDeclaration(
        name="signoz_search_logs",
        description=(
            "Search recent logs for a specific service. Returns log body, severity, "
            "and structured attributes. Use to find specific error messages, "
            "exception stack traces, and business context (user IDs, amounts, etc.)."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "service": types.Schema(
                    type=types.Type.STRING,
                    description="Exact service name as known to SigNoz.",
                ),
                "limit": types.Schema(
                    type=types.Type.INTEGER,
                    description="Max log entries to return (default 10, max 30).",
                ),
            },
            required=["service"],
        ),
    ),
    types.FunctionDeclaration(
        name="signoz_list_alerts",
        description=(
            "List all currently firing alerts in SigNoz. Use to understand "
            "whether multiple services are alerting simultaneously (cascade vs. "
            "isolated failure)."
        ),
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
])

_REPORT_TOOL = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="report_findings",
        description=(
            "Call this ONLY when you have enough evidence to produce a complete, "
            "grounded diagnosis. This ends the investigation."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "root_cause_service": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "The service actually causing the failure. May differ from "
                        "the alerting service if errors are propagating upstream."
                    ),
                ),
                "error_message": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "The EXACT error text observed in traces or logs. Quote it "
                        "verbatim. Never paraphrase. Empty string only if no error "
                        "message was found."
                    ),
                ),
                "affected_user_pattern": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "Specific user segment or attribute pattern visible in the "
                        "failing requests (e.g. 'gold-tier loyalty users', "
                        "'POST /api/checkout requests'). Empty string if not applicable."
                    ),
                ),
                "affected_service_p99_ms": types.Schema(
                    type=types.Type.NUMBER,
                    description="p99 latency in milliseconds of the alerting service. 0 if unknown.",
                ),
                "root_cause_error_rate_pct": types.Schema(
                    type=types.Type.NUMBER,
                    description="Error rate percentage of the root cause service. 0 if unknown.",
                ),
                "confidence_pct": types.Schema(
                    type=types.Type.INTEGER,
                    description=(
                        "How confident you are in this diagnosis (0-100). Be honest: "
                        "80+ means you saw a specific error message directly linking "
                        "cause and effect. 50-79 means strong circumstantial evidence. "
                        "Below 50 means inconclusive."
                    ),
                ),
                "confidence_reasoning": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "1-2 sentences explaining WHY you have this confidence level, "
                        "citing specific evidence you observed "
                        "(e.g. 'Every failed trace contains status_message X and "
                        "attribute loyalty_level=gold')."
                    ),
                ),
                "recommended_fix_steps": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description=(
                        "2-5 specific, actionable fix steps. Each step should be "
                        "concrete enough for a developer to act on immediately. "
                        "No generic advice."
                    ),
                ),
                "slack_one_liner": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "One sentence under 120 characters for on-call awareness. "
                        "Include specific numbers and the affected service. "
                        "Example: 'payment rejecting gold-tier users (41% error rate), "
                        "checkout p99 2934ms'."
                    ),
                ),
                "github_body": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "Full GitHub issue body in Markdown. Must include: "
                        "1) An evidence table with actual measured values. "
                        "2) The exact error message in a code block. "
                        "3) Fix steps as a checklist (- [ ] item). "
                        "4) SigNoz links as clickable markdown links. "
                        "Write as if you are a senior SRE handing off to the on-call engineer."
                    ),
                ),
                "signoz_links": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description=(
                        "URLs to relevant SigNoz pages. Use webUrl values from tool "
                        "responses where available (these are deep links). "
                        "Include service dashboard and specific trace links."
                    ),
                ),
            },
            required=[
                "root_cause_service", "error_message", "affected_user_pattern",
                "affected_service_p99_ms", "root_cause_error_rate_pct",
                "confidence_pct", "confidence_reasoning",
                "recommended_fix_steps", "slack_one_liner", "github_body",
            ],
        ),
    ),
])

_SYSTEM_PROMPT = """You are PatchNoz, an autonomous SRE investigation agent.
You receive a SigNoz alert and investigate it by calling SigNoz monitoring tools
to find the real root cause -- specific, evidence-grounded, not generic.

## Investigation strategy

1. Start with signoz_list_services to see which services have elevated p99 or error rates.
2. Call signoz_search_traces on the alerting service to find slow/failing spans and their operation names.
3. If a downstream dependency looks suspicious, search its traces and logs too.
4. Keep drilling until you find the ACTUAL error message -- the verbatim text from a
   status_message, log body, or exception that explains what is failing.
5. Look for patterns: does every failing trace share a common attribute (user tier,
   region, endpoint, card type)?

## When to stop

Call report_findings when you have:
- The root cause service (may differ from the alerting service)
- A specific, verbatim error message from traces or logs
- Enough to write 2-5 concrete fix steps

If after 8 tool calls you still lack a clear error message, call report_findings
with what you have and explain the uncertainty in confidence_reasoning.

## Output quality

- error_message: quote verbatim, never paraphrase
- slack_one_liner: include actual numbers, under 120 chars
- github_body: write as a senior SRE handing off to on-call -- include an evidence
  table with real measured values, the error in a code block, and a fix checklist
- Do NOT repeat the same tool call with identical arguments
- Use webUrl values from tool responses for signoz_links (they are deep links)
"""


class LLMInvestigationAgent:
    """
    Investigates a single SigNoz Alert using a Gemini bare-API tool-calling loop.

    The agent calls SigNoz MCP tools iteratively until it has enough evidence,
    then produces an InvestigationResult by invoking the report_findings pseudo-tool.
    """

    def __init__(
        self,
        adapter: Optional[SigNozMCPAdapter] = None,
        api_key: str = GEMINI_API_KEY,
        model: str = GEMINI_MODEL,
        max_tool_calls: int = MAX_TOOL_CALLS,
        base_url: str = SIGNOZ_BASE_URL,
    ):
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com"
            )
        self.adapter = adapter or default_adapter
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.max_tool_calls = max_tool_calls
        self.base_url = base_url

    def investigate(self, alert: IncidentAlert) -> InvestigationResult:
        """Run the full investigation loop and return a grounded InvestigationResult."""
        with start_span(
            "patchnoz.llm.investigate",
            {"incident.id": alert.incident_id, "service.affected": alert.affected_service},
        ) as span:
            result = self._run_loop(alert)
            span.set_attribute("llm.model", self.model)
            span.set_attribute("llm.tool_calls", result.tool_calls_made)
            span.set_attribute("llm.confidence_pct", result.confidence_pct)
            return result

    def _run_loop(self, alert: IncidentAlert) -> InvestigationResult:
        initial_message = (
            f"Investigate this SigNoz alert:\n\n"
            f"- Alert name: {alert.alert_name}\n"
            f"- Affected service: {alert.affected_service}\n"
            f"- Severity: {alert.severity}\n"
            f"- Condition: {alert.condition or 'not specified'}\n"
            f"- Time window: last {alert.time_range}\n"
            f"- SigNoz base URL: {self.base_url}\n\n"
            f"Start investigating. Find the root cause."
        )

        contents: List[types.Content] = [
            types.Content(role="user", parts=[types.Part(text=initial_message)])
        ]

        tool_call_count = 0
        seen_calls: set = set()  # deduplicate identical tool calls

        while tool_call_count < self.max_tool_calls:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    tools=[_SIGNOZ_TOOLS, _REPORT_TOOL],
                    system_instruction=_SYSTEM_PROMPT,
                    temperature=0.1,  # low temperature for deterministic investigation
                ),
            )

            # Append the model turn to history
            contents.append(response.candidates[0].content)

            if not response.function_calls:
                # Model returned text without tool call -- unexpected but handled
                print(f"[LLMAgent] Model returned text instead of tool call. Stopping.")
                break

            fn_responses: List[types.Part] = []

            for fc in response.function_calls:
                if fc.name == "report_findings":
                    return self._build_result(fc.args, alert, tool_call_count)

                # Deduplicate: skip if we've already made the same call
                call_key = (fc.name, json.dumps(fc.args or {}, sort_keys=True))
                if call_key in seen_calls:
                    fn_responses.append(self._make_fn_response(
                        fc.name,
                        {"note": "Skipped: identical call already made. Try a different tool or call report_findings."},
                    ))
                    continue
                seen_calls.add(call_key)

                # Execute the SigNoz tool
                raw_result, error = self._call_signoz_tool(fc.name, fc.args or {})
                tool_call_count += 1

                if error:
                    fn_responses.append(self._make_fn_response(fc.name, {"error": error}))
                else:
                    formatted = _format_tool_response(fc.name, raw_result)
                    fn_responses.append(self._make_fn_response(fc.name, {"result": formatted}))

            if fn_responses:
                contents.append(types.Content(role="user", parts=fn_responses))

        # Max tool calls reached -- ask for a best-effort report
        print(f"[LLMAgent] Reached max tool calls ({self.max_tool_calls}). Requesting best-effort report.")
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=(
                f"You have used {tool_call_count} tool calls. "
                "Call report_findings now with your best current assessment. "
                "Be honest about uncertainty in confidence_reasoning."
            ))],
        ))

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                tools=[_REPORT_TOOL],
                system_instruction=_SYSTEM_PROMPT,
                temperature=0.1,
            ),
        )

        if response.function_calls:
            for fc in response.function_calls:
                if fc.name == "report_findings":
                    return self._build_result(fc.args, alert, tool_call_count)

        # Ultimate fallback if model still won't call report_findings
        return InvestigationResult(
            alert_id=alert.incident_id,
            alert_name=alert.alert_name,
            severity=alert.severity,
            affected_service=alert.affected_service,
            root_cause_service=alert.affected_service,
            error_message="",
            affected_user_pattern="",
            affected_service_p99_ms=0.0,
            root_cause_error_rate_pct=0.0,
            confidence_pct=0,
            confidence_reasoning="Investigation did not complete -- model did not return report_findings.",
            recommended_fix_steps=["Investigate manually in SigNoz."],
            slack_one_liner=f"Investigation incomplete for {alert.affected_service} -- check SigNoz manually.",
            github_body="Investigation did not complete. Please investigate manually in SigNoz.",
            signoz_links=[f"{self.base_url}/services/{alert.affected_service}"],
            tool_calls_made=tool_call_count,
            model=self.model,
        )

    def _call_signoz_tool(
        self, tool_name: str, args: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Execute a SigNoz MCP tool and return (result, error)."""
        with start_span("patchnoz.llm.tool_call", {"mcp.tool": tool_name}):
            try:
                if tool_name == "signoz_list_services":
                    return self.adapter.list_services(), None
                elif tool_name == "signoz_search_traces":
                    service = args.get("service", "")
                    limit = min(int(args.get("limit", 5)), 20)
                    return self.adapter.search_traces(service, limit=limit), None
                elif tool_name == "signoz_search_logs":
                    service = args.get("service", "")
                    limit = min(int(args.get("limit", 10)), 30)
                    return self.adapter.search_logs(service, limit=limit), None
                elif tool_name == "signoz_list_alerts":
                    return self.adapter.list_alerts(), None
                else:
                    return {}, f"Unknown tool: {tool_name}"
            except Exception as exc:
                return {}, str(exc)

    @staticmethod
    def _make_fn_response(name: str, payload: Dict[str, Any]) -> types.Part:
        return types.Part(
            function_response=types.FunctionResponse(name=name, response=payload)
        )

    def _build_result(
        self,
        args: Dict[str, Any],
        alert: IncidentAlert,
        tool_calls_made: int,
    ) -> InvestigationResult:
        """Parse report_findings arguments into an InvestigationResult."""
        steps = args.get("recommended_fix_steps", [])
        if isinstance(steps, str):
            steps = [s.strip() for s in steps.split("\n") if s.strip()]

        links = args.get("signoz_links", [])
        if not links:
            links = [f"{self.base_url}/services/{alert.affected_service}"]

        return InvestigationResult(
            alert_id=alert.incident_id,
            alert_name=alert.alert_name,
            severity=alert.severity,
            affected_service=alert.affected_service,
            root_cause_service=str(args.get("root_cause_service", alert.affected_service)),
            error_message=str(args.get("error_message", "")),
            affected_user_pattern=str(args.get("affected_user_pattern", "")),
            affected_service_p99_ms=float(args.get("affected_service_p99_ms", 0.0)),
            root_cause_error_rate_pct=float(args.get("root_cause_error_rate_pct", 0.0)),
            confidence_pct=int(args.get("confidence_pct", 0)),
            confidence_reasoning=str(args.get("confidence_reasoning", "")),
            recommended_fix_steps=list(steps),
            slack_one_liner=str(args.get("slack_one_liner", "")),
            github_body=str(args.get("github_body", "")),
            signoz_links=list(links),
            tool_calls_made=tool_calls_made,
            model=self.model,
        )
