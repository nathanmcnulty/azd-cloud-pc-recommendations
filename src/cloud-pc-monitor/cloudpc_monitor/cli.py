"""Safe fixture-backed validation command for the monitor."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .config import Settings
from .graph_client import GraphSnapshot
from .notifications import TeamsNotifier
from .report import NullReportExporter
from .service import MonitorService
from .state import InMemoryStateStore


class FixtureCollector:
    def __init__(self, fixture_dir: Path) -> None:
        self.fixture_dir = fixture_dir

    def collect(self, settings: Settings) -> GraphSnapshot:
        return GraphSnapshot(
            cloud_pcs=_load(self.fixture_dir / "cloudpcs.json"),
            managed_devices=_load(self.fixture_dir / "managed-devices.json"),
            recommendations=(
                _load(self.fixture_dir / "recommendations.json")
                if settings.recommendations_enabled
                else []
            ),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "tests" / "fixtures",
    )
    parser.add_argument(
        "--now",
        default="2026-09-19T12:00:00Z",
        help="UTC timestamp used for deterministic rule evaluation.",
    )
    parser.add_argument(
        "--passes",
        type=_positive_int,
        default=2,
        help="Number of fixture passes. Two passes demonstrate grace periods.",
    )
    parser.add_argument(
        "--advance-hours",
        type=float,
        default=2.0,
        help="Hours advanced between fixture passes.",
    )
    args = parser.parse_args()

    environment = dict(__import__("os").environ)
    environment.update(
        {
            "DRY_RUN": "true",
            "NOTIFICATIONS_ENABLED": "false",
            "SEND_NOTIFICATIONS_IN_DRY_RUN": "false",
            "STORAGE_ACCOUNT_URL": "",
        }
    )
    settings = Settings.from_environment(environment)
    current_time = [_parse_datetime(args.now)]
    service = MonitorService(
        settings,
        collector=FixtureCollector(args.fixtures),
        state=InMemoryStateStore(),
        reporter=NullReportExporter(),
        notifier=TeamsNotifier(settings),
        clock=lambda: current_time[0],
    )
    report = {}
    for pass_number in range(args.passes):
        report = service.run()
        if pass_number < args.passes - 1:
            from datetime import timedelta

            current_time[0] += timedelta(hours=args.advance_hours)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _load(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError(f"Fixture '{path}' must contain an array.")
    return payload


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise ValueError("must be at least 1")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
