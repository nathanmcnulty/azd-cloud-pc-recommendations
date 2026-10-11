from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "cloud-pc-monitor"))
from cloudpc_monitor.acknowledgements import StateError, identity
from cloudpc_monitor.ack_cli import main
from cloudpc_monitor.config import Settings
from cloudpc_monitor.graph_client import GraphSnapshot
from cloudpc_monitor.notifications import TeamsNotifier
from cloudpc_monitor.rules import evaluate_alerts, normalize_records
from cloudpc_monitor.state import InMemoryStateStore

NOW = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
REQUEST = "4e1c9e82-f31f-4ce2-bdb5-117863b3d178"
TENANT = "e44f2194-f24f-4b7c-a98f-bf161303bb25"


def activate(store, now=NOW):
    records = normalize_records(GraphSnapshot(cloud_pcs=[{
        "id": "pc-fixture", "status": "provisioned",
        "provisionedDateTime": "2026-01-01T00:00:00Z"}]))
    return evaluate_alerts(records, Settings.from_environment({}).rules, store, now=now)


def acknowledge(store, fingerprint, **changes):
    value = identity(store.get_alert(fingerprint))
    args = dict(episode=value["episode"], revision=value["ackRevision"], request_id=REQUEST,
                actor="fixture-operator", expires_at=NOW + timedelta(hours=1), now=NOW)
    args.update(changes)
    return store.acknowledge_alert(fingerprint, **args)


class Session:
    def __init__(self):
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append(kwargs)
        return type("Response", (), {"status_code": 200, "headers": {}})()


class AcknowledgementTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStateStore()
        self.alerts = activate(self.store)
        self.fp = self.alerts[0].fingerprint

    def test_actual_flow_suppresses_then_expiry_and_interval_reallow(self):
        session = Session()
        notifier = TeamsNotifier(Settings.from_environment({"DRY_RUN": "false",
            "TEAMS_WEBHOOK_URL": "https://fixture.invalid/notify",
            "NOTIFICATION_RENOTIFY_HOURS": "24"}), session=session)
        event = acknowledge(self.store, self.fp)
        self.assertEqual(event["request"]["actorSource"], "operator_asserted")
        self.assertEqual(event["recordedAt"], "2026-10-11T12:00:00Z")
        self.assertEqual(notifier.deliver(self.alerts, self.store, now=NOW)["status"], "none")
        self.assertEqual(session.calls, [])
        activate(self.store, NOW + timedelta(minutes=30))
        self.assertTrue(self.store.get_alert(self.fp)["acknowledged"])
        expired = activate(self.store, NOW + timedelta(hours=1))
        self.assertFalse(self.store.get_alert(self.fp)["acknowledged"])
        self.assertEqual(notifier.deliver(expired, self.store, now=NOW + timedelta(hours=1))["status"], "sent")
        self.assertEqual(notifier.deliver(expired, self.store, now=NOW + timedelta(hours=2))["status"], "none")
        value = self.store.get_alert(self.fp)
        self.assertEqual(value["notificationCount"], 1)
        self.assertEqual({e["kind"] for e in self.store.history(self.fp)["events"]}, {"acknowledged", "expired"})

    def test_resolution_reactivation_new_episode_preserves_history_and_delivery_metadata(self):
        acknowledge(self.store, self.fp)
        old = self.store.get_alert(self.fp)
        self.store.mark_notified(self.fp, "2026-10-11T11:00:00Z")
        self.store.alerts[self.fp]["futureField"] = {"keep": True}
        evaluate_alerts([], Settings.from_environment({}).rules, self.store, now=NOW + timedelta(minutes=1))
        self.assertFalse(self.store.get_alert(self.fp)["active"])
        activate(self.store, NOW + timedelta(minutes=2))
        new = self.store.get_alert(self.fp)
        self.assertNotEqual(old["episode"], new["episode"])
        self.assertFalse(new["acknowledged"])
        self.assertEqual(new["notificationCount"], 1)
        self.assertEqual(new["futureField"], {"keep": True})
        self.assertEqual({e["kind"] for e in self.store.history(self.fp)["events"]}, {"acknowledged", "resolved", "reopened"})
        with self.assertRaisesRegex(StateError, "stale_identity"):
            acknowledge(self.store, self.fp, episode=old["episode"],
                        request_id="f1d795f2-2e58-4088-8d7a-7fc59458e104")

    def test_identical_replay_after_timer_and_expiry_is_noop_and_changed_request_rejected(self):
        value = self.store.get_alert(self.fp)
        event = acknowledge(self.store, self.fp)
        activate(self.store, NOW + timedelta(hours=2))
        before = deepcopy(self.store.alerts)
        replay = acknowledge(self.store, self.fp, episode=value["episode"], revision=0,
                             now=NOW + timedelta(hours=2))
        self.assertEqual(event, replay)
        self.assertEqual(before, self.store.alerts)
        with self.assertRaisesRegex(StateError, "request_reused"):
            acknowledge(self.store, self.fp, actor="other")

    def test_missing_inactive_wrong_revision_and_invalid_types_no_mutation(self):
        for fp, args, code in [
            ("a" * 64, {}, "missing_alert"), (self.fp, {"revision": 1}, "stale_identity"),
            (self.fp, {"revision": True}, "invalid_request"),
            (self.fp, {"actor": "https://secret.invalid/token"}, "invalid_request"),
            (self.fp, {"expires_at": NOW}, "invalid_request"),
            (self.fp, {"request_id": REQUEST + "\n"}, "invalid_request")]:
            before = deepcopy(self.store.alerts)
            if fp not in self.store.alerts:
                args.update(episode=self.store.get_alert(self.fp)["episode"], revision=0)
                with self.assertRaisesRegex(StateError, code):
                    self.store.acknowledge_alert(fp, request_id=REQUEST, actor="op", now=NOW,
                        expires_at=NOW + timedelta(hours=1), **args)
            else:
                with self.assertRaisesRegex(StateError, code):
                    acknowledge(self.store, fp, **args)
            self.assertEqual(before, self.store.alerts)
        self.store.mark_alert_inactive(self.fp, "2026-10-11T12:01:00Z")
        with self.assertRaisesRegex(StateError, "inactive_alert"):
            acknowledge(self.store, self.fp)

    def test_legacy_unknown_ack_survives_migration_and_bounded_history_pages(self):
        old = self.store.alerts[self.fp]
        old.pop("episode"); old.pop("ackRevision")
        old.update(acknowledged=True, acknowledgedAt="2026-10-01T00:00:00Z")
        activate(self.store, NOW)
        self.assertTrue(self.store.get_alert(self.fp)["acknowledged"])
        self.assertNotIn("ackActor", self.store.get_alert(self.fp))
        acknowledge(self.store, self.fp)
        activate(self.store, NOW + timedelta(hours=2))
        first = self.store.history(self.fp, limit=1)
        second = self.store.history(self.fp, limit=1, cursor=first["cursor"])
        self.assertEqual(len(first["events"]), 1)
        self.assertNotEqual(first["events"], second["events"])
        with self.assertRaisesRegex(StateError, "invalid_request"):
            self.store.history(self.fp, limit=101)

    def test_timer_conflict_recomputes_against_concurrent_ack(self):
        commit = self.store._commit_alert
        called = []
        def interleave(fp, value, token, event):
            if not called:
                called.append(True)
                acknowledge(self.store, fp)
            return commit(fp, value, token, event)
        with patch.object(self.store, "_commit_alert", side_effect=interleave):
            activate(self.store, NOW + timedelta(minutes=2))
        self.assertTrue(self.store.get_alert(self.fp)["acknowledged"])
        self.assertEqual(self.store.get_alert(self.fp)["ackRevision"], 1)
        self.assertEqual(len(self.store.history(self.fp)["events"]), 1)

    def test_lost_ack_resolved_by_event_not_repeated_mutation(self):
        commit = self.store._commit_alert
        calls = []
        def lost(*args):
            calls.append(args)
            commit(*args)
            raise StateError("outcome_unknown")
        with patch.object(self.store, "_commit_alert", side_effect=lost):
            event = acknowledge(self.store, self.fp)
        self.assertEqual(event["kind"], "acknowledged")
        self.assertEqual(len(calls), 1)
        with patch.object(self.store, "_commit_alert", side_effect=StateError("outcome_unknown")):
            with self.assertRaisesRegex(StateError, "outcome_unknown"):
                acknowledge(self.store, self.fp, request_id="f1d795f2-2e58-4088-8d7a-7fc59458e104")

    def test_bounded_conflict_refuses_without_history(self):
        with patch.object(self.store, "_commit_alert", return_value=False) as commit:
            with self.assertRaisesRegex(StateError, "state_conflict"):
                acknowledge(self.store, self.fp)
        self.assertEqual(commit.call_count, 4)
        self.assertEqual(self.store.history(self.fp)["events"], [])

    def test_cli_invalid_input_zero_factory_and_safe_error(self):
        argv = ["--account-name", "fixtureaccount", "--tenant-id", TENANT, "--table", "CloudPcState",
                "acknowledge", "--fingerprint", self.fp, "--episode", self.store.get_alert(self.fp)["episode"],
                "--revision", "0", "--request-id", REQUEST, "--actor", "https://secret.invalid/canary",
                "--expires-at", "2026-10-11T13:00:00Z"]
        with patch("cloudpc_monitor.ack_cli.create_store") as factory, redirect_stdout(StringIO()) as output:
            self.assertEqual(main(argv, store_factory=factory, clock=lambda: NOW), 1)
        factory.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()), {"status": "failed", "code": "invalid_request"})

    def test_actual_cli_show_ack_history_never_collection_or_notification(self):
        base = ["--account-name", "fixtureaccount", "--tenant-id", TENANT, "--table", "CloudPcState"]
        self.store.alerts[self.fp]["actionUrl"] = "https://secret.invalid/canary"
        with patch("cloudpc_monitor.service.MonitorService.from_environment", side_effect=AssertionError()), \
                patch.object(TeamsNotifier, "deliver", side_effect=AssertionError()):
            for tail in [["show", "--fingerprint", self.fp],
                         ["acknowledge", "--fingerprint", self.fp, "--episode", self.store.get_alert(self.fp)["episode"],
                          "--revision", "0", "--request-id", REQUEST, "--actor", "fixture-op",
                          "--expires-at", "2026-10-11T13:00:00Z"],
                         ["history", "--fingerprint", self.fp]]:
                with redirect_stdout(StringIO()) as output:
                    self.assertEqual(main(base + tail, store_factory=lambda _: self.store, clock=lambda: NOW), 0)
                self.assertNotIn("canary", output.getvalue())
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(main(base + ["show", "--fingerprint", self.fp],
                store_factory=lambda _: (_ for _ in ()).throw(RuntimeError("CANARY"))), 1)
        self.assertNotIn("CANARY", output.getvalue())

    def test_cli_expired_and_foreign_stored_identity_fail_closed(self):
        base = ["--account-name", "fixtureaccount", "--tenant-id", TENANT, "--table", "CloudPcState"]
        args = base + ["acknowledge", "--fingerprint", self.fp, "--episode", self.store.get_alert(self.fp)["episode"],
            "--revision", "0", "--request-id", REQUEST, "--actor", "op", "--expires-at", "2026-10-11T12:00:00Z"]
        with patch("cloudpc_monitor.ack_cli.create_store") as factory, redirect_stdout(StringIO()):
            self.assertEqual(main(args, store_factory=factory, clock=lambda: NOW), 1)
        factory.assert_not_called()
        self.store.alerts[self.fp]["fingerprint"] = "b" * 64
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(main(base + ["show", "--fingerprint", self.fp],
                store_factory=lambda _: self.store, clock=lambda: NOW), 1)
        self.assertEqual(json.loads(output.getvalue())["code"], "invalid_state")

    def test_cli_projection_discards_unknown_fields_and_rejects_raw_url_actor(self):
        acknowledge(self.store, self.fp)
        event = self.store._events[self.fp, REQUEST]
        event["unknown"] = "CANARY-URL-token"
        event["request"]["unknown"] = "CANARY-URL-token"
        self.assertNotIn("CANARY", json.dumps(self.store.history(self.fp)))
        event["request"]["actor"] = "https://CANARY.invalid/token"
        with self.assertRaises(StateError):
            self.store.history(self.fp)

    def test_cli_parser_error_is_closed_without_echoing_argument(self):
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(main(["--CANARY-token-url"]), 1)
        self.assertEqual(json.loads(output.getvalue()), {"status": "failed", "code": "invalid_request"})

    def test_source_permission_evidence_matches_actual_files(self):
        import hashlib
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "azd-permissions.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["coverage"], "partial")
        self.assertTrue(manifest["gaps"])
        for requirement in manifest["requirements"]:
            for evidence in requirement["evidence"]:
                self.assertEqual(hashlib.sha256((root / evidence["path"]).read_bytes()).hexdigest(), evidence["sha256"])


if __name__ == "__main__":
    unittest.main()
