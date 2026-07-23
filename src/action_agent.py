"""
Action Agent

Turns an InvestigationResult into concrete Actions: a Slack post and a
GitHub issue. Each action degrades gracefully to a dry-run when its
credentials are not configured.
"""

from typing import Callable, List

from src.adapters import github, slack
from src.models import ActionResult, InvestigationResult
from src.self_telemetry import start_span


class ActionAgent:
    """Executes remediation actions for a completed investigation."""

    def execute(self, result: InvestigationResult) -> List[ActionResult]:
        """Runs Slack + GitHub actions and returns their results."""
        with start_span("patchnoz.action.execute", {"incident.id": result.alert_id}):
            return [
                self._run_action("slack", result, slack.post_summary),
                self._run_action("github", result, github.create_issue),
            ]

    @staticmethod
    def _run_action(
        name: str,
        result: InvestigationResult,
        action_fn: Callable[[InvestigationResult], ActionResult],
    ) -> ActionResult:
        with start_span(f"patchnoz.action.{name}", {"action.name": name}) as span:
            try:
                action_result = action_fn(result)
            except Exception as e:
                span.record_exception(e)
                action_result = ActionResult(
                    name=name, status="failed", details={"error": str(e)}
                )
            span.set_attribute("action.status", action_result.status)
            return action_result
