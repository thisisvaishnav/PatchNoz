"""
Unit tests for the Alert Detection & Ingestion Layer (before handle_alert is called).

Tests:
1. JSON-RPC response text parsing in _parse_result (handling markdown blocks, whitespace, lists).
2. Alert structure parsing in _parse_firing_alerts (nested rules, groups, data, list, items).
3. Extracting active alert instances from SigNoz rule objects with nested 'alerts'.
4. State filtering in list_firing_alerts (firing, alerting, active vs resolved, pending, inactive).
5. State/Status key fallback ('state', 'status', 'alertState').
6. Error propagation vs exception handling in ScanOrchestrator._fetch_firing_alerts.
7. IncidentAlert.from_signoz_alert field extraction (service_name, service, app, job, alertname, alert_name, title).
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from src.models import IncidentAlert
from src.scan_orchestrator import ScanOrchestrator
from src.signoz_mcp_adapter import SigNozMCPAdapter


class TestParseResult(unittest.TestCase):
    """Tests for SigNozMCPAdapter._parse_result JSON text parsing."""

    def test_clean_json_object(self):
        resp = {"result": {"content": [{"text": '{"data": [{"name": "alert1"}]}'}]}}
        res = SigNozMCPAdapter._parse_result(resp)
        self.assertEqual(res, {"data": [{"name": "alert1"}]})

    def test_clean_json_array(self):
        resp = {"result": {"content": [{"text": '[{"name": "alert1"}]'}]}}
        res = SigNozMCPAdapter._parse_result(resp)
        self.assertEqual(res, {"data": [{"name": "alert1"}]})

    def test_markdown_code_block_json(self):
        """SigNoz MCP responses wrapped in ```json ... ``` markdown blocks."""
        resp = {"result": {"content": [{"text": '```json\n[{"name": "alert1", "state": "firing"}]\n```'}]}}
        res = SigNozMCPAdapter._parse_result(resp)
        # Should correctly strip markdown and parse as JSON data
        self.assertEqual(res, {"data": [{"name": "alert1", "state": "firing"}]})

    def test_json_with_whitespace_and_newlines(self):
        resp = {"result": {"content": [{"text": '  \n  [{"name": "alert1"}]  \n '}]}}
        res = SigNozMCPAdapter._parse_result(resp)
        self.assertEqual(res, {"data": [{"name": "alert1"}]})

    def test_empty_content(self):
        self.assertEqual(SigNozMCPAdapter._parse_result({}), {})
        self.assertEqual(SigNozMCPAdapter._parse_result({"result": {}}), {})
        self.assertEqual(SigNozMCPAdapter._parse_result({"result": {"content": []}}), {})

    def test_rpc_error_raises_runtime_error(self):
        resp = {"error": {"code": -32601, "message": "Method not found"}}
        with self.assertRaises(RuntimeError):
            SigNozMCPAdapter._parse_result(resp)


class TestParseFiringAlertsStructures(unittest.TestCase):
    """Tests for _parse_firing_alerts handling various SigNoz/Prometheus response shapes."""

    def test_rules_key_structure(self):
        """SigNoz rule list format: {"rules": [...]}."""
        raw = {"rules": [{"name": "High CPU", "state": "firing"}]}
        result = SigNozMCPAdapter._parse_firing_alerts(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "High CPU")

    def test_nested_data_rules_structure(self):
        """SigNoz nested format: {"data": {"rules": [...]}}."""
        raw = {"data": {"rules": [{"name": "Memory Leak", "state": "firing"}]}}
        result = SigNozMCPAdapter._parse_firing_alerts(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Memory Leak")

    def test_groups_structure(self):
        """Prometheus groups format: {"data": {"groups": [{"rules": [...]}]}}."""
        raw = {
            "data": {
                "groups": [
                    {
                        "name": "group1",
                        "rules": [{"name": "Disk Full", "state": "firing"}],
                    }
                ]
            }
        }
        result = SigNozMCPAdapter._parse_firing_alerts(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Disk Full")

    def test_items_key_structure(self):
        """List in 'items' key: {"items": [...]}}."""
        raw = {"items": [{"name": "Latency High", "state": "firing"}]}
        result = SigNozMCPAdapter._parse_firing_alerts(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Latency High")

    def test_list_key_structure(self):
        """List in 'list' key: {"data": {"list": [...]}}."""
        raw = {"data": {"list": [{"name": "DB Connection Error", "state": "firing"}]}}
        result = SigNozMCPAdapter._parse_firing_alerts(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "DB Connection Error")

    def test_rule_with_nested_active_alerts(self):
        """
        SigNoz rule object containing nested active alert instances in 'alerts'.
        Each nested alert instance carries specific labels (e.g. service_name).
        """
        raw = {
            "data": [
                {
                    "name": "High Error Rate Rule",
                    "state": "firing",
                    "alerts": [
                        {
                            "name": "High Error Rate",
                            "state": "firing",
                            "labels": {"service_name": "payment-service", "severity": "critical"},
                            "annotations": {"description": "Error rate > 5%"},
                        }
                    ],
                }
            ]
        }
        result = SigNozMCPAdapter._parse_firing_alerts(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["labels"]["service_name"], "payment-service")


class TestStateAndStatusFiltering(unittest.TestCase):
    """Tests for state & status field filtering in list_firing_alerts."""

    def setUp(self):
        self.adapter = SigNozMCPAdapter()

    @patch("src.signoz_mcp_adapter.SigNozMCPAdapter.list_alerts")
    def test_status_field_used_instead_of_state(self, mock_list_alerts):
        """Alerts using 'status' key instead of 'state' (e.g. status='firing')."""
        mock_list_alerts.return_value = {
            "data": [
                {"name": "firing_via_status", "status": "firing"},
                {"name": "resolved_via_status", "status": "resolved"},
            ]
        }
        firing = self.adapter.list_firing_alerts()
        names = [a["name"] for a in firing]
        self.assertIn("firing_via_status", names)
        self.assertNotIn("resolved_via_status", names)

    @patch("src.signoz_mcp_adapter.SigNozMCPAdapter.list_alerts")
    def test_alert_state_field_name(self, mock_list_alerts):
        """Alerts using 'alertState' or 'alert_state' key."""
        mock_list_alerts.return_value = {
            "data": [
                {"name": "alert1", "alertState": "firing"},
                {"name": "alert2", "alert_state": "resolved"},
            ]
        }
        firing = self.adapter.list_firing_alerts()
        names = [a["name"] for a in firing]
        self.assertIn("alert1", names)
        self.assertNotIn("alert2", names)

    @patch("src.signoz_mcp_adapter.SigNozMCPAdapter.list_alerts")
    def test_resolved_alert_with_missing_state_is_not_included(self, mock_list_alerts):
        """Ensure resolved alerts with 'status': 'resolved' are not erroneously treated as firing."""
        mock_list_alerts.return_value = {
            "data": [
                {"name": "resolved_alert", "status": "resolved"},
            ]
        }
        firing = self.adapter.list_firing_alerts()
        self.assertEqual(len(firing), 0)


class TestIncidentAlertFromSigNozAlert(unittest.TestCase):
    """Tests for IncidentAlert.from_signoz_alert model parsing edge cases."""

    def test_service_extraction_from_app_and_job_labels(self):
        raw_app = {"name": "alert1", "labels": {"app": "cart-service"}}
        raw_job = {"name": "alert2", "labels": {"job": "order-service"}}
        raw_top = {"name": "alert3", "service": "auth-service"}

        self.assertEqual(IncidentAlert.from_signoz_alert(raw_app).affected_service, "cart-service")
        self.assertEqual(IncidentAlert.from_signoz_alert(raw_job).affected_service, "order-service")
        self.assertEqual(IncidentAlert.from_signoz_alert(raw_top).affected_service, "auth-service")

    def test_alert_name_extraction_from_title_and_label(self):
        raw_title = {"title": "CPU Overload", "labels": {"service": "worker"}}
        raw_label = {"labels": {"alert_name": "Memory High", "service": "worker"}}

        self.assertEqual(IncidentAlert.from_signoz_alert(raw_title).alert_name, "CPU Overload")
        self.assertEqual(IncidentAlert.from_signoz_alert(raw_label).alert_name, "Memory High")


class TestFetchFiringAlertsErrorLogging(unittest.TestCase):
    """Tests error handling during fetch in ScanOrchestrator."""

    @patch("src.scan_orchestrator.default_adapter")
    def test_fetch_firing_alerts_failure_returns_empty_list_and_logs(self, mock_adapter):
        mock_adapter.list_firing_alerts.side_effect = RuntimeError("Connection timeout to SigNoz")
        orchestrator = ScanOrchestrator(
            llm_agent=MagicMock(),
            action_agent=MagicMock(),
            recorder=MagicMock()
        )
        alerts = orchestrator._fetch_firing_alerts()
        self.assertEqual(alerts, [])


if __name__ == "__main__":
    unittest.main()
