"""Orchestration for one Cloud PC monitoring run."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Callable
from uuid import uuid4

from .config import Settings
from .graph_client import GraphClient, GraphSnapshot
from .notifications import TeamsNotifier
from .report import BlobReportExporter
from .rules import evaluate_alerts, isoformat, normalize_records
from .state import TableStateStore


class MonitorService:
    """Collect, evaluate, notify, and export without performing remediation."""

    def __init__(
        self,
        settings: Settings,
        *,
        collector: Any,
        state: Any,
        reporter: Any,
        notifier: Any,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.collector = collector
        self.state = state
        self.reporter = reporter
        self.notifier = notifier
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @classmethod
    def from_environment(cls) -> "MonitorService":
        settings = Settings.from_environment()
        if not settings.storage_account_url:
            raise RuntimeError(
                "STORAGE_ACCOUNT_URL is required for the deployed monitor."
            )

        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()
        return cls(
            settings,
            collector=GraphClient(
                api_version=settings.graph_api_version,
                credential=credential,
                max_retries=settings.max_retries,
            ),
            state=TableStateStore(
                _table_endpoint(settings.storage_account_url),
                credential,
                settings.state_table_name,
            ),
            reporter=BlobReportExporter(
                account_url=settings.storage_account_url,
                credential=credential,
                container_name=settings.report_container_name,
            ),
            notifier=TeamsNotifier(settings),
        )

    def run(self) -> dict[str, Any]:
        observed_at = self.clock().astimezone(timezone.utc)
        snapshot: GraphSnapshot = self.collector.collect(self.settings)
        records = normalize_records(
            snapshot, action_url=self.settings.intune_cloud_pc_url
        )
        alerts = evaluate_alerts(
            records,
            self.settings.rules,
            self.state,
            now=observed_at,
            global_suppressions=self.settings.global_suppressions,
        )
        notifications = self.notifier.deliver(
            alerts, self.state, now=observed_at
        )
        run_id = str(uuid4())
        report = {
            "schemaVersion": "1.0",
            "runId": run_id,
            "observedAt": isoformat(observed_at),
            "dryRun": self.settings.dry_run,
            "graphApiVersion": self.settings.graph_api_version,
            "collection": {
                "cloudPcCount": len(snapshot.cloud_pcs),
                "managedDeviceCount": len(snapshot.managed_devices),
                "recommendationCount": len(snapshot.recommendations),
            },
            "alertCount": len(alerts),
            "alerts": [alert.as_payload() for alert in alerts],
            "notifications": notifications,
            "warnings": list(snapshot.warnings),
            "cloudPcs": [_compact_record(record) for record in records],
            "remediation": {
                "enabled": False,
                "executed": False,
                "reason": "not_implemented_in_first_milestone",
            },
        }
        report_uri = self.reporter.write(report)
        if report_uri:
            report["reportUri"] = report_uri
        self.state.record_run(run_id, report)
        logging.info(
            "Cloud PC monitor report persisted: runId=%s alerts=%s warnings=%s",
            run_id,
            len(alerts),
            len(snapshot.warnings),
        )
        return report


def _table_endpoint(blob_endpoint: str) -> str:
    if ".blob." not in blob_endpoint:
        raise RuntimeError(
            "STORAGE_ACCOUNT_URL must be the Blob endpoint for the deployed monitor."
        )
    return blob_endpoint.replace(".blob.", ".table.", 1).rstrip("/")


def _compact_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "displayName": record.get("display_name"),
        "userPrincipalName": record.get("user_principal_name"),
        "status": record.get("status"),
        "connectivityStatus": record.get("connectivity_status"),
        "managedDeviceId": record.get("managed_device_id"),
        "managedDeviceName": record.get("managed_device_name"),
        "lastLoginAt": _date_value(record.get("last_login_at")),
        "lastSyncAt": _date_value(record.get("last_sync_at")),
        "complianceState": record.get("compliance_state"),
        "managementState": record.get("management_state"),
        "recommendationUsageInsight": record.get("recommendation_usage_insight"),
        "recommendedPlanName": record.get("recommendation_plan_name"),
    }


def _date_value(value: Any) -> str | None:
    return isoformat(value) if isinstance(value, datetime) else None
