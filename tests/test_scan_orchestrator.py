"""
Unit tests for ScanOrchestrator alert detection, shape normalization, state filtering, and alert parsing.
"""

import unittest
from unittest.mock import MagicMock, patch
from typing import Any, Dict

from src.scan_orchestrator import ScanOrchestrator, _parse_firing_alerts
from src.models import IncidentAlert


class TestParseFiringAlerts(unittest.TestCase):
    """Tests for _parse_firing_alerts shape normalization."""

    def test_flat_list_in_data(self):
        raw = {"data": [{"name": "alert1", "state": "firing"}, {"name": "alert2", "state": "firing"}]}
        result = _parse_firing_alerts(raw)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "alert1")

    def test_nested_data_alerts(self):
        raw = {"data": {"alerts": [{"name": "alert1", "state": "firing"}]}}
        result = _parse_firing_alerts(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "alert1")

    def test_nested_data_data(self):
        raw = {"data": {"data": [{"name": "alert1", "state": "firing"}]}}
        result = _parse_firing_alerts(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "alert1")

    def test_top_level_alerts_key(self):
        raw = {"alerts": [{"name": "alert1", "state": "firing"}]}
        result = _parse_firing_alerts(raw)
        self.assertEqual(len(result), 1)

    def test_empty_or_invalid_structures(self):
        self.assertEqual(_parse_firing_alerts({}), [])
        self.assertEqual(_parse_firing_alerts(None), [])  # type: ignore
        self.assertEqual(_parse_firing_alerts("not a dict"), [])  # type: ignore
        self.assertEqual(_parse_firing_alerts({"data": None}), [])
        self.assertEqual(_parse_firing_alerts({"data": "string"}), [])


class TestStateFiltering(unittest.TestCase):
    """Tests for state filtering in SigNozMCPAdapter.list_firing_alerts."""

    def setUp(self):
        from src.signoz_mcp_adapter import SigNozMCPAdapter
        self.adapter = SigNozMCPAdapter()
        self.orchestrator = ScanOrchestrator(
            llm_agent=MagicMock(),
            action_agent=MagicMock(),
            recorder=MagicMock()
        )

    @patch("src.signoz_mcp_adapter.SigNozMCPAdapter.list_alerts")
    def test_state_filter_valid_states(self, mock_list_alerts):
        mock_list_alerts.return_value = {
            "data": [
                {"name": "alert_firing", "state": "firing"},
                {"name": "alert_alerting", "state": "alerting"},
                {"name": "alert_active", "state": "active"},
                {"name": "alert_uppercase", "state": "FIRING"},
                {"name": "alert_empty_state", "state": ""},
                {"name": "alert_no_state_key"},
            ]
        }
        firing = self.adapter.list_firing_alerts()
        names = [a["name"] for a in firing]
        self.assertEqual(
            names,
            [
                "alert_firing",
                "alert_alerting",
                "alert_active",
                "alert_uppercase",
                "alert_empty_state",
                "alert_no_state_key",
            ]
        )

    @patch("src.signoz_mcp_adapter.SigNozMCPAdapter.list_alerts")
    def test_state_filter_excludes_non_firing_states(self, mock_list_alerts):
        mock_list_alerts.return_value = {
            "data": [
                {"name": "alert_resolved", "state": "resolved"},
                {"name": "alert_pending", "state": "pending"},
                {"name": "alert_inactive", "state": "inactive"},
                {"name": "alert_disabled", "state": "disabled"},
                {"name": "alert_ok", "state": "ok"},
                {"name": "alert_normal", "state": "normal"},
            ]
        }
        firing = self.adapter.list_firing_alerts()
        self.assertEqual(len(firing), 0)

    @patch("src.signoz_mcp_adapter.SigNozMCPAdapter.list_alerts")
    def test_state_filter_null_state_handling(self, mock_list_alerts):
        """
        Tests behavior when state is explicitly None/null: {"state": null}.
        State is safely normalized so explicit state=None is treated like missing key (passes through).
        """
        mock_list_alerts.return_value = {
            "data": [
                {"name": "alert_null_state", "state": None},
            ]
        }
        firing = self.adapter.list_firing_alerts()
        self.assertEqual(len(firing), 1)
        self.assertEqual(firing[0]["name"], "alert_null_state")

    @patch("src.signoz_mcp_adapter.SigNozMCPAdapter.list_alerts")
    def test_state_filter_non_dict_element_handling(self, mock_list_alerts):
        """
        Tests how list_firing_alerts safely ignores non-dict items in the list.
        """
        mock_list_alerts.return_value = {
            "data": [
                {"name": "valid_alert", "state": "firing"},
                "unexpected_string_element",
            ]
        }
        firing = self.adapter.list_firing_alerts()
        self.assertEqual(len(firing), 1)
        self.assertEqual(firing[0]["name"], "valid_alert")


class TestIncidentAlertFromSigNozAlert(unittest.TestCase):
    """Tests for IncidentAlert.from_signoz_alert model parsing."""

    def test_parse_with_labels(self):
        raw = {
            "name": "High CPU Usage",
            "labels": {
                "service_name": "checkout-service",
                "severity": "critical"
            },
            "annotations": {"description": "CPU exceeded 90%"}
        }
        alert = IncidentAlert.from_signoz_alert(raw)
        self.assertEqual(alert.alert_name, "High CPU Usage")
        self.assertEqual(alert.affected_service, "checkout-service")
        self.assertEqual(alert.severity, "critical")
        self.assertEqual(alert.condition, "CPU exceeded 90%")
        self.assertEqual(alert.incident_id, "checkout-service-high-cpu-usage")

    def test_parse_generator_url_with_service_name(self):
        raw = {
            "alertname": "LatencySpike",
            "generatorURL": "http://localhost:8080/alerts?service_name%3Dpayment-service%26env%3Dprod",
            "severity": "warning"
        }
        alert = IncidentAlert.from_signoz_alert(raw)
        self.assertEqual(alert.affected_service, "payment-service")

    def test_parse_generator_url_without_service_name(self):
        """
        Tests generatorURL when no service parameter is inside URL.
        Should fall back to 'unknown'.
        """
        raw = {
            "alertname": "MemoryLeak",
            "generatorURL": "http://localhost:8080/alerts/detail/123",
        }
        alert = IncidentAlert.from_signoz_alert(raw)
        self.assertEqual(alert.affected_service, "unknown")


class TestScanOrchestratorRunOnce(unittest.TestCase):
    """Tests for ScanOrchestrator.run_once complete cycle."""

    @patch("src.scan_orchestrator.find_open_issue")
    @patch("src.scan_orchestrator.default_adapter")
    def test_run_once_with_firing_alerts(self, mock_adapter, mock_find_issue):
        mock_adapter.list_firing_alerts.return_value = [
            {
                "name": "High Error Rate",
                "state": "firing",
                "labels": {"service": "frontend", "severity": "error"}
            }
        ]
        mock_find_issue.return_value = None  # No existing open issue

        mock_llm = MagicMock()
        mock_llm.investigate.return_value = MagicMock(
            root_cause_service="frontend",
            confidence_pct=90
        )
        mock_action = MagicMock()
        mock_action.execute.return_value = []
        mock_recorder = MagicMock()

        orchestrator = ScanOrchestrator(
            llm_agent=mock_llm,
            action_agent=mock_action,
            recorder=mock_recorder
        )

        runs = orchestrator.run_once()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].alert.alert_name, "High Error Rate")
        self.assertEqual(runs[0].alert.affected_service, "frontend")


if __name__ == "__main__":
    unittest.main()
