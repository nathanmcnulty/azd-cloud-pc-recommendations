from __future__ import annotations

from datetime import datetime, timezone
import sys
from pathlib import Path
import unittest


APP_ROOT = Path(__file__).resolve().parents[1] / "src" / "cloud-pc-monitor"
sys.path.insert(0, str(APP_ROOT))

from cloudpc_monitor.config import Settings  # noqa: E402
from cloudpc_monitor.notifications import TeamsNotifier  # noqa: E402
from cloudpc_monitor.rules import Alert  # noqa: E402
from cloudpc_monitor.state import InMemoryStateStore  # noqa: E402


class FakeResponse:
    status_code = 200
    headers = {}
    text = "ok"


class FakeSession:
    def __init__(self):
        self.payloads = []

    def post(self, url, **kwargs):
        self.payloads.append((url, kwargs))
        return FakeResponse()


class NotificationTests(unittest.TestCase):
    def test_webhook_delivery_is_deduplicated(self) -> None:
        settings = Settings.from_environment(
            {
                "DRY_RUN": "false",
                "TEAMS_WEBHOOK_URL": "https://workflow.test/webhook",
                "NOTIFICATION_RENOTIFY_HOURS": "24",
            }
        )
        session = FakeSession()
        notifier = TeamsNotifier(settings, session=session)
        state = InMemoryStateStore()
        now = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
        alert = Alert(
            fingerprint="fingerprint",
            rule_id="unused-cloud-pc",
            severity="medium",
            route="cloud-pc-operations",
            cloud_pc_id="pc-1",
            title="Unused Cloud PC",
            summary="Review the device.",
            first_seen_at=now,
            detected_at=now,
            action_url="https://intune.test/",
            evidence={"userPrincipalName": "user@example.com"},
        )
        state.upsert_alert(alert.as_state())

        first = notifier.deliver([alert], state, now=now)
        second = notifier.deliver(
            [alert], state, now=now.replace(hour=13)
        )

        self.assertEqual(first["status"], "sent")
        self.assertEqual(second["status"], "none")
        self.assertEqual(len(session.payloads), 1)
        self.assertEqual(
            session.payloads[0][1]["json"]["attachments"][0]["content"]["type"],
            "AdaptiveCard",
        )


if __name__ == "__main__":
    unittest.main()
