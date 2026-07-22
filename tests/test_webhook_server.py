"""
Unit tests for the SigNoz alert webhook receiver (src/webhook_server.py).

Tests:
1. _extract_alerts normalizes both the real Alertmanager batch shape and a
   single raw alert dict (manual/curl testing).
2. _is_authorized enforces PATCHNOZ_WEBHOOK_TOKEN when set, and allows
   everything through when unset.
3. POST /webhook/signoz: happy path accepts firing alerts and skips
   resolved ones, invalid JSON -> 400, empty/unrecognized payload -> 400,
   missing/incorrect token -> 401 when a token is configured.
"""

import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

from src import webhook_server
from src.webhook_server import _extract_alerts, app


ALERTMANAGER_PAYLOAD = {
    "receiver": "patchnoz",
    "status": "firing",
    "alerts": [
        {
            "status": "firing",
            "labels": {"alertname": "HighErrorRate", "severity": "critical", "service_name": "checkout"},
            "annotations": {"description": "error rate > 5%"},
            "startsAt": "2024-01-01T00:00:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "",
            "fingerprint": "abc123",
        },
        {
            "status": "resolved",
            "labels": {"alertname": "HighErrorRate", "severity": "critical", "service_name": "checkout"},
            "annotations": {"description": "error rate > 5%"},
            "fingerprint": "abc123",
        },
    ],
    "groupLabels": {"alertname": "HighErrorRate"},
    "commonLabels": {"alertname": "HighErrorRate"},
    "commonAnnotations": {},
    "externalURL": "http://alertmanager:9093",
    "version": "4",
    "groupKey": "{}/{}:{alertname=\"HighErrorRate\"}",
}


class TestExtractAlerts(unittest.TestCase):
    def test_batch_shape(self):
        alerts = _extract_alerts(ALERTMANAGER_PAYLOAD)
        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0]["status"], "firing")

    def test_single_alert_dict(self):
        raw = {"alertname": "MemoryLeak", "labels": {"service": "payment"}}
        alerts = _extract_alerts(raw)
        self.assertEqual(alerts, [raw])

    def test_unrecognized_payload(self):
        self.assertEqual(_extract_alerts({"foo": "bar"}), [])
        self.assertEqual(_extract_alerts("not a dict"), [])
        self.assertEqual(_extract_alerts(None), [])

    def test_alerts_key_with_non_dict_items_filtered(self):
        raw = {"alerts": [{"status": "firing"}, "not a dict", 42]}
        alerts = _extract_alerts(raw)
        self.assertEqual(alerts, [{"status": "firing"}])


class TestIsAuthorized(unittest.TestCase):
    """
    _is_authorized() takes a Starlette Request, so these are exercised
    end-to-end through the real /webhook/signoz route rather than by
    constructing a Request by hand.
    """

    def test_unset_token_allows_everything(self):
        with patch.object(webhook_server, "WEBHOOK_TOKEN", ""), \
             patch.object(webhook_server, "_investigate_in_background"):
            client = TestClient(app)
            resp = client.post("/webhook/signoz", json=ALERTMANAGER_PAYLOAD)
            self.assertNotEqual(resp.status_code, 401)

    def test_set_token_rejects_missing_or_wrong_token(self):
        with patch.object(webhook_server, "WEBHOOK_TOKEN", "secret123"):
            client = TestClient(app)
            resp = client.post("/webhook/signoz", json=ALERTMANAGER_PAYLOAD)
            self.assertEqual(resp.status_code, 401)

            resp = client.post(
                "/webhook/signoz",
                json=ALERTMANAGER_PAYLOAD,
                headers={"x-patchnoz-webhook-token": "wrong"},
            )
            self.assertEqual(resp.status_code, 401)

    def test_set_token_accepts_correct_header(self):
        with patch.object(webhook_server, "WEBHOOK_TOKEN", "secret123"), \
             patch.object(webhook_server, "_investigate_in_background"):
            client = TestClient(app)
            resp = client.post(
                "/webhook/signoz",
                json=ALERTMANAGER_PAYLOAD,
                headers={"x-patchnoz-webhook-token": "secret123"},
            )
            self.assertEqual(resp.status_code, 202)

    def test_set_token_accepts_correct_query_param(self):
        with patch.object(webhook_server, "WEBHOOK_TOKEN", "secret123"), \
             patch.object(webhook_server, "_investigate_in_background"):
            client = TestClient(app)
            resp = client.post(
                "/webhook/signoz?token=secret123",
                json=ALERTMANAGER_PAYLOAD,
            )
            self.assertEqual(resp.status_code, 202)


class TestSignozWebhookEndpoint(unittest.TestCase):
    def setUp(self):
        # No auth configured for these endpoint-behavior tests.
        self._token_patcher = patch.object(webhook_server, "WEBHOOK_TOKEN", "")
        self._token_patcher.start()
        self.client = TestClient(app)

    def tearDown(self):
        self._token_patcher.stop()

    def test_invalid_json_returns_400(self):
        resp = self.client.post(
            "/webhook/signoz",
            data="not json",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_empty_payload_returns_400(self):
        resp = self.client.post("/webhook/signoz", json={"foo": "bar"})
        self.assertEqual(resp.status_code, 400)

    @patch.object(webhook_server, "_investigate_in_background")
    def test_firing_alert_accepted_resolved_skipped(self, mock_investigate):
        resp = self.client.post("/webhook/signoz", json=ALERTMANAGER_PAYLOAD)
        self.assertEqual(resp.status_code, 202)
        body = resp.json()
        self.assertEqual(len(body["accepted"]), 1)
        self.assertEqual(body["skipped_resolved"], 1)
        self.assertEqual(body["errors"], [])
        # Dispatched on a background thread -- only the one firing alert,
        # never the resolved one.
        mock_investigate.assert_called_once()
        called_alert = mock_investigate.call_args[0][0]
        self.assertEqual(called_alert.incident_id, "checkout-higherrorrate")

    def test_single_raw_alert_object_accepted(self):
        raw = {
            "status": "firing",
            "alertname": "LatencySpike",
            "labels": {"service_name": "payment", "severity": "warning"},
        }
        with patch.object(webhook_server, "_investigate_in_background"):
            resp = self.client.post("/webhook/signoz", json=raw)
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(len(resp.json()["accepted"]), 1)

    def test_healthz(self):
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
