"""
Action Agent

Turns a RootCauseSummary into concrete remediation actions: a Slack
summary and a GitHub issue carrying the suggested fix. Each action
degrades to a safe dry-run when its credentials aren't configured, so
the pipeline is always runnable out of the box - real actions activate
automatically once SLACK_WEBHOOK_URL / GITHUB_TOKEN+OWNER+REPO are set.
"""

from typing import Callable, List

from src.adapters import github, slack
from src.models import ActionResult, RootCauseSummary
from src.self_telemetry import start_span


class ActionAgent:
    """Executes remediation actions for a diagnosed incident."""

    def execute(self, summary: RootCauseSummary) -> List[ActionResult]:
        """Runs every configured action and returns their results, in order."""
        with start_span("patchnoz.action.execute", {"incident.id": summary.incident_id}):
            return [
                self._run_action("slack", summary, slack.post_summary),
                self._run_action("github", summary, github.create_issue),
            ]

    @staticmethod
    def _run_action(
        name: str,
        summary: RootCauseSummary,
        action_fn: Callable[[RootCauseSummary], ActionResult],
    ) -> ActionResult:
        with start_span(f"patchnoz.action.{name}", {"action.name": name}) as span:
            try:
                result = action_fn(summary)
            except Exception as e:
                span.record_exception(e)
                result = ActionResult(name=name, status="failed", details={"error": str(e)})
            span.set_attribute("action.status", result.status)
            return result
