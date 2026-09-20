from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest


APP_ROOT = Path(__file__).resolve().parents[1] / "src" / "cloud-pc-monitor"
sys.path.insert(0, str(APP_ROOT))

from cloudpc_monitor.config import Settings  # noqa: E402
from cloudpc_monitor.graph_client import GraphSnapshot  # noqa: E402
from cloudpc_monitor.rules import evaluate_alerts, normalize_records  # noqa: E402
from cloudpc_monitor.state import InMemoryStateStore  # noqa: E402


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class RuleTests(unittest.TestCase):
    def test_never_used_cloud_pc_uses_provisioning_age_when_login_is_null(self) -> None:
        settings = Settings.from_environment({})
        snapshot = GraphSnapshot(
            cloud_pcs=[
                {
                    "id": "never-used",
                    "displayName": "CPC-NEVER-USED",
                    "status": "provisioned",
                    "provisionedDateTime": "2026-08-01T12:00:00Z",
                }
            ]
        )
        records = normalize_records(snapshot)
        state = InMemoryStateStore()

        alerts = evaluate_alerts(
            records,
            settings.rules,
            state,
            now=datetime(2026, 9, 19, 12, tzinfo=timezone.utc),
        )

        self.assertEqual([alert.rule_id for alert in alerts], ["unused-cloud-pc"])

    def test_three_milestone_alerts_respect_grace_then_activate(self) -> None:
        settings = Settings.from_environment({})
        snapshot = GraphSnapshot(
            cloud_pcs=load("cloudpcs.json"),
            managed_devices=load("managed-devices.json"),
        )
        records = normalize_records(snapshot, action_url="https://intune.test/")
        state = InMemoryStateStore()
        first = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)

        first_alerts = evaluate_alerts(
            records, settings.rules, state, now=first
        )
        self.assertEqual([alert.rule_id for alert in first_alerts], ["unused-cloud-pc"])

        second_alerts = evaluate_alerts(
            records,
            settings.rules,
            state,
            now=first + timedelta(hours=2),
        )
        self.assertEqual(
            {alert.rule_id for alert in second_alerts},
            {
                "unused-cloud-pc",
                "provisioning-failure",
                "unhealthy-stale-device",
            },
        )
        self.assertEqual(len(state.list_alerts()), 3)

    def test_suppression_prevents_alert_and_durable_state(self) -> None:
        settings = Settings.from_environment(
            {"ALERT_SUPPRESSIONS": "provisioning-failure"}
        )
        snapshot = GraphSnapshot(
            cloud_pcs=load("cloudpcs.json"),
            managed_devices=load("managed-devices.json"),
        )
        records = normalize_records(snapshot)
        state = InMemoryStateStore()
        now = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)

        alerts = evaluate_alerts(
            records,
            settings.rules,
            state,
            now=now,
            global_suppressions=settings.global_suppressions,
        )

        self.assertNotIn("provisioning-failure", {alert.rule_id for alert in alerts})
        self.assertFalse(
            any(item["ruleId"] == "provisioning-failure" for item in state.list_alerts())
        )


if __name__ == "__main__":
    unittest.main()
