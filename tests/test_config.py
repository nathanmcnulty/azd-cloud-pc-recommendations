from __future__ import annotations

import sys
from pathlib import Path
import unittest


APP_ROOT = Path(__file__).resolve().parents[1] / "src" / "cloud-pc-monitor"
sys.path.insert(0, str(APP_ROOT))

from cloudpc_monitor.config import ConfigurationError, Settings  # noqa: E402


class ConfigurationTests(unittest.TestCase):
    def test_safe_defaults_are_dry_run_and_recommendation_report_is_opt_in(self) -> None:
        settings = Settings.from_environment({})

        self.assertTrue(settings.dry_run)
        self.assertFalse(settings.recommendations_enabled)
        self.assertFalse(settings.send_notifications_in_dry_run)
        self.assertEqual(settings.unused_cloud_pc_days, 30)
        self.assertEqual(
            [rule.id for rule in settings.rules],
            [
                "unused-cloud-pc",
                "provisioning-failure",
                "unhealthy-stale-device",
            ],
        )

    def test_json_rules_can_change_thresholds_and_routing(self) -> None:
        settings = Settings.from_environment(
            {
                "CLOUD_PC_RULES_JSON": (
                    '[{"id":"unused-cloud-pc","enabled":true,'
                    '"severity":"low","thresholdDays":7,'
                    '"gracePeriodMinutes":15,"route":"finops"}]'
                )
            }
        )

        rule = settings.rules[0]
        self.assertEqual(rule.threshold_days, 7)
        self.assertEqual(rule.grace_period_minutes, 15)
        self.assertEqual(rule.route, "finops")
        self.assertEqual(rule.severity, "low")

    def test_invalid_boolean_is_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            Settings.from_environment({"DRY_RUN": "sometimes"})


if __name__ == "__main__":
    unittest.main()
