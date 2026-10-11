"""Offline characterization of current consumer boundaries for CPC-004.

These execute the existing Python consumer, not a replacement event engine or
canonical-contract adapter. Synthetic HTTP responses never leave the process.
"""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest

APP_ROOT = Path(__file__).resolve().parents[1] / "src" / "cloud-pc-monitor"
sys.path.insert(0, str(APP_ROOT))

from cloudpc_monitor.cli import FixtureCollector
from cloudpc_monitor.config import Settings
from cloudpc_monitor.notifications import TeamsNotifier
from cloudpc_monitor.report import NullReportExporter
from cloudpc_monitor.rules import Alert, fingerprint_for
from cloudpc_monitor.service import MonitorService
from cloudpc_monitor.state import InMemoryStateStore

NOW = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
FIXTURES = Path(__file__).resolve().parent / "fixtures"
CANARY_URL = "https://workflow.invalid/callback?sig=synthetic-assessment-canary"


class Response:
    def __init__(self, status=200, text="ok"):
        self.status_code = status
        self.text = text
        self.headers = {}


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


def alert(index):
    return Alert(
        fingerprint=fingerprint_for("unused-cloud-pc", f"synthetic-{index}"),
        rule_id="unused-cloud-pc", severity="medium", route="cloud-pc-operations",
        cloud_pc_id=f"synthetic-{index}", title="Synthetic alert", summary="Review only.",
        first_seen_at=NOW, detected_at=NOW, action_url="https://intune.microsoft.com/",
        evidence={},
    )


def enabled_settings(**overrides):
    return Settings.from_environment({"DRY_RUN": "false", "TEAMS_WEBHOOK_URL": CANARY_URL, **overrides})


class ComponentAssessmentTests(unittest.TestCase):
    def test_actual_service_report_is_an_aggregate_not_management_or_route_evidence(self):
        settings = Settings.from_environment({"NOTIFICATIONS_ENABLED": "false", "TEAMS_WEBHOOK_URL": CANARY_URL, "REMEDIATION_ENABLED": "true"})
        state = InMemoryStateStore()
        now = [NOW]
        service = MonitorService(settings, collector=FixtureCollector(FIXTURES), state=state,
                                 reporter=NullReportExporter(), notifier=TeamsNotifier(settings),
                                 clock=lambda: now[0])
        service.run()
        now[0] += timedelta(hours=2)
        report = service.run()
        self.assertEqual(report["schemaVersion"], "1.0")
        self.assertEqual(report["alertCount"], 3)
        self.assertEqual(report["notifications"]["candidateCount"], report["alertCount"])
        self.assertEqual(state.runs[report["runId"]], report)
        self.assertEqual(report["remediation"], {"enabled": False, "executed": False, "reason": "not_implemented_in_first_milestone"})
        self.assertNotIn(CANARY_URL, json.dumps(report))
        # Required canonical management/report identities do not exist here.
        self.assertTrue({"reportType", "mode", "checks", "outcome"}.isdisjoint(report))
        self.assertTrue({"eventId", "idempotencyKey", "attempt", "evidence"}.isdisjoint(report["notifications"]))

    def test_partial_batch_failure_retains_successful_state_but_has_no_per_event_receipts(self):
        alerts = [alert(index) for index in range(11)]
        state = InMemoryStateStore()
        for item in alerts:
            state.upsert_alert(item.as_state())
        session = Session([Response(), Response(400, CANARY_URL)])
        notifier = TeamsNotifier(enabled_settings(), session=session)
        # Execute the repaired boundary; aggregate result semantics stay intact.
        with self.assertLogs(level="ERROR") as logs:
            result = notifier.deliver(alerts, state, now=NOW)
        self.assertEqual(result, {"status": "failed", "candidateCount": 11, "sentCount": 10, "reason": "webhook_request_failed"})
        self.assertEqual(len(session.calls), 2)
        self.assertTrue(all(state.get_alert(item.fingerprint)["notificationCount"] == 1 for item in alerts[:10]))
        self.assertIsNone(state.get_alert(alerts[-1].fingerprint)["lastNotifiedAt"])
        self.assertNotIn(CANARY_URL, json.dumps(result))
        self.assertNotIn(CANARY_URL, " ".join(logs.output))
        self.assertIn("http_rejected", " ".join(logs.output))

    def test_acknowledgement_and_completed_delivery_have_the_same_aggregate_reason(self):
        item = alert(0)
        receipts = []
        for acknowledged in (False, True):
            state = InMemoryStateStore()
            state.upsert_alert(item.as_state())
            if acknowledged:
                state.upsert_alert({**state.get_alert(item.fingerprint), "acknowledged": True, "acknowledgedAt": NOW.isoformat()})
            else:
                state.mark_notified(item.fingerprint, NOW.isoformat())
            session = Session([])
            receipts.append(TeamsNotifier(enabled_settings(), session=session).deliver([item], state, now=NOW))
            self.assertEqual(session.calls, [])
        self.assertEqual(receipts[0], receipts[1])
        self.assertEqual(receipts[0]["reason"], "deduplicated_or_acknowledged")

    def test_selected_missing_destination_is_currently_skip_not_canonical_failure(self):
        state = InMemoryStateStore()
        item = alert(0)
        state.upsert_alert(item.as_state())
        result = TeamsNotifier(enabled_settings(TEAMS_WEBHOOK_URL=""), session=Session([])).deliver([item], state, now=NOW)
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "webhook_not_configured")
        self.assertNotIn("failure", result)

    def test_http_acceptance_is_distinct_from_recipient_delivery_and_renotification(self):
        item = alert(0)
        state = InMemoryStateStore()
        state.upsert_alert(item.as_state())
        session = Session([Response(202), Response(202)])
        notifier = TeamsNotifier(enabled_settings(), session=session)
        first = notifier.deliver([item], state, now=NOW)
        later = notifier.deliver([item], state, now=NOW + timedelta(hours=24))
        self.assertEqual(first["status"], "sent")
        self.assertEqual(later["status"], "sent")
        self.assertEqual(state.get_alert(item.fingerprint)["notificationCount"], 2)
        self.assertEqual(set(first), {"status", "candidateCount", "sentCount", "reason"})
        self.assertNotIn(CANARY_URL, json.dumps(first))
        self.assertEqual(session.calls[0][1]["timeout"], 15)


if __name__ == "__main__":
    unittest.main()
