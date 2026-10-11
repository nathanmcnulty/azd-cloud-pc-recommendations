"""Exercise Requests, the notifier, monitor and timer boundary without networking."""
from datetime import timedelta
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1] / "src" / "cloud-pc-monitor"
sys.path.insert(0, str(APP_ROOT))

import requests
from requests.adapters import BaseAdapter
from cloudpc_monitor.cli import FixtureCollector
from cloudpc_monitor.notifications import NotificationError, TeamsNotifier
from cloudpc_monitor.report import NullReportExporter
from cloudpc_monitor.service import MonitorService
from cloudpc_monitor.state import InMemoryStateStore
from tests.test_component_assessment import CANARY_URL, FIXTURES, NOW, alert, enabled_settings

SECRET = "Authorization: Bearer synthetic-credential-canary " + CANARY_URL


class NoBodyResponse(requests.Response):
    @property
    def text(self):
        raise AssertionError("Provider response.text must never be inspected")


class FixtureAdapter(BaseAdapter):
    """A real Requests prepared-request boundary with no native HTTP adapter."""
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []

    def send(self, request, **kwargs):
        self.calls.append((request, kwargs))
        if request.url != CANARY_URL:
            raise AssertionError("Unexpected synthetic destination")
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        response = NoBodyResponse()
        response.status_code = outcome
        response._content = SECRET.encode()
        response.request = request
        response.headers["Retry-After"] = "0"
        return response

    def close(self):
        pass


def session_for(outcomes):
    adapter = FixtureAdapter(outcomes)
    session = requests.Session()
    session.trust_env = False
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session, adapter


class NotificationSafetyTests(unittest.TestCase):
    def assert_safe_logs(self, captured, code):
        rendered = " ".join(captured.output)
        self.assertIn(code, rendered)
        self.assertNotIn(CANARY_URL, rendered)
        self.assertNotIn("synthetic-credential-canary", rendered)
        self.assertNotIn("Authorization", rendered)
        self.assertTrue(all(record.exc_info is None for record in captured.records))

    def deliver(self, outcomes, count=1):
        items = [alert(index) for index in range(count)]
        state = InMemoryStateStore()
        for item in items:
            state.upsert_alert(item.as_state())
        session, adapter = session_for(outcomes)
        waits = []
        notifier = TeamsNotifier(enabled_settings(), session=session, sleeper=waits.append)
        with self.assertLogs(level="ERROR") as captured:
            result = notifier.deliver(items, state, now=NOW)
        self.assertNotIn(CANARY_URL, json.dumps(result))
        self.assertNotIn("synthetic-credential-canary", json.dumps(result))
        return result, state, items, adapter, waits, captured

    def test_nonretryable_body_is_never_read_or_logged(self):
        result, state, items, adapter, waits, logs = self.deliver([400])
        self.assert_safe_logs(logs, "http_rejected")
        self.assertEqual(result, {"status": "failed", "candidateCount": 1, "sentCount": 0, "reason": "webhook_request_failed"})
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(waits, [])
        self.assertIsNone(state.get_alert(items[0].fingerprint)["lastNotifiedAt"])

    def test_retry_exhaustion_preserves_four_attempts_and_bounded_waits(self):
        for status in (429, 500, 502, 503, 504):
            with self.subTest(status=status):
                result, _, _, adapter, waits, logs = self.deliver([status] * 4)
                self.assert_safe_logs(logs, "http_retry_exhausted")
                self.assertEqual(result["sentCount"], 0)
                self.assertEqual(len(adapter.calls), 4)
                self.assertEqual(waits, [0.0, 0.0, 0.0])

    def test_requests_transport_errors_are_classified_without_raw_fallback(self):
        for error_type, code in (
            (requests.exceptions.ReadTimeout, "transport_timeout"),
            (requests.exceptions.ConnectTimeout, "transport_timeout"),
            (requests.exceptions.ConnectionError, "transport_connection_failed"),
            (requests.exceptions.SSLError, "transport_connection_failed"),
            (requests.exceptions.RequestException, "transport_request_failed"),
            (requests.exceptions.InvalidURL, "transport_request_failed"),
            (RuntimeError, "transport_failed"),
        ):
            with self.subTest(error=error_type.__name__):
                result, _, _, adapter, waits, logs = self.deliver([error_type(SECRET)])
                self.assert_safe_logs(logs, code)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["sentCount"], 0)
                # Transport errors previously escaped without retrying. They
                # now return a safe failure, without inventing new retry policy.
                self.assertEqual(len(adapter.calls), 1)
                self.assertEqual(waits, [])

    def test_partial_batch_transport_failure_keeps_only_successful_notification_state(self):
        result, state, items, adapter, _, logs = self.deliver([202, requests.exceptions.ConnectionError(SECRET)], count=11)
        self.assert_safe_logs(logs, "transport_connection_failed")
        self.assertEqual(result["sentCount"], 10)
        self.assertEqual(len(adapter.calls), 2)
        self.assertTrue(all(state.get_alert(item.fingerprint)["notificationCount"] == 1 for item in items[:10]))
        self.assertIsNone(state.get_alert(items[-1].fingerprint)["lastNotifiedAt"])

    def test_unknown_notification_error_codes_cannot_retain_arbitrary_text(self):
        error = NotificationError(SECRET)
        self.assertEqual(error.code, "transport_failed")
        self.assertEqual(str(error), "transport_failed")

    def test_safe_exception_has_no_raw_transport_cause_or_context(self):
        session, _ = session_for([requests.exceptions.ConnectionError(SECRET)])
        notifier = TeamsNotifier(enabled_settings(), session=session)
        with self.assertRaises(NotificationError) as caught:
            notifier._send({})
        self.assertEqual(str(caught.exception), "transport_connection_failed")
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)

    def test_actual_timer_and_monitor_persist_safe_failure_without_an_escaping_exception(self):
        module = importlib.import_module("function_app")
        handler = module.app.get_functions()[0].get_user_function()
        for outcome, code in ((400, "http_rejected"), (requests.exceptions.ReadTimeout(SECRET), "transport_timeout")):
            with self.subTest(outcome=type(outcome).__name__):
                session, adapter = session_for([outcome, outcome])
                now = [NOW]
                state = InMemoryStateStore()
                service = MonitorService(enabled_settings(), collector=FixtureCollector(FIXTURES), state=state,
                                         reporter=NullReportExporter(), notifier=TeamsNotifier(enabled_settings(), session=session),
                                         clock=lambda: now[0])
                with patch.object(module.MonitorService, "from_environment", return_value=service), self.assertLogs(level="INFO") as logs:
                    handler(SimpleNamespace(past_due=False))
                    now[0] += timedelta(hours=2)
                    handler(SimpleNamespace(past_due=False))
                self.assert_safe_logs(logs, code)
                self.assertIn("Cloud PC monitor completed", " ".join(logs.output))
                self.assertEqual(len(adapter.calls), 2)
                reports = list(state.runs.values())
                self.assertTrue(all(report["notifications"]["status"] == "failed" for report in reports))
                self.assertFalse(reports[-1]["remediation"]["executed"])
                self.assertNotIn(CANARY_URL, json.dumps(reports))
                self.assertNotIn("synthetic-credential-canary", json.dumps(reports))


if __name__ == "__main__":
    unittest.main()
