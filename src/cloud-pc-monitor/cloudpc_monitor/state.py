"""Durable state abstractions with an in-memory test implementation."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from typing import Any


class InMemoryStateStore:
    """State store used by deterministic fixture runs and unit tests."""

    def __init__(self) -> None:
        self.alerts: dict[str, dict[str, Any]] = {}
        self.observations: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}

    def get_alert(self, fingerprint: str) -> dict[str, Any] | None:
        value = self.alerts.get(fingerprint)
        return deepcopy(value) if value is not None else None

    def list_alerts(self) -> list[dict[str, Any]]:
        return [deepcopy(value) for value in self.alerts.values()]

    def upsert_alert(self, value: dict[str, Any]) -> None:
        self.alerts[value["fingerprint"]] = deepcopy(value)

    def mark_alert_inactive(self, fingerprint: str, resolved_at: str) -> None:
        value = self.alerts.get(fingerprint)
        if value is not None:
            value["active"] = False
            value["resolvedAt"] = resolved_at

    def mark_notified(self, fingerprint: str, notified_at: str) -> None:
        value = self.alerts.get(fingerprint)
        if value is not None:
            value["lastNotifiedAt"] = notified_at
            value["notificationCount"] = int(value.get("notificationCount", 0)) + 1

    def acknowledge_alert(self, fingerprint: str, acknowledged_at: str) -> None:
        value = self.alerts.get(fingerprint)
        if value is not None:
            value["acknowledged"] = True
            value["acknowledgedAt"] = acknowledged_at

    def record_observation(self, key: str, observed_at: datetime) -> datetime:
        existing = self.observations.get(key)
        if existing is None:
            self.observations[key] = {
                "key": key,
                "firstSeenAt": observed_at,
                "lastSeenAt": observed_at,
            }
            return observed_at
        existing["lastSeenAt"] = observed_at
        return existing["firstSeenAt"]

    def list_observations(self) -> list[dict[str, Any]]:
        return [deepcopy(value) for value in self.observations.values()]

    def delete_observation(self, key: str) -> None:
        self.observations.pop(key, None)

    def record_run(self, run_id: str, report: dict[str, Any]) -> None:
        self.runs[run_id] = deepcopy(report)


class TableStateStore:
    """Azure Table Storage implementation scoped to one dedicated table."""

    def __init__(self, endpoint: str, credential: Any, table_name: str) -> None:
        from azure.data.tables import TableClient

        self._table = TableClient(
            endpoint=endpoint,
            credential=credential,
            table_name=table_name,
        )
        self._table.create_table_if_not_exists()

    def get_alert(self, fingerprint: str) -> dict[str, Any] | None:
        return self._get_payload("alert", fingerprint)

    def list_alerts(self) -> list[dict[str, Any]]:
        return self._query_payloads("alert")

    def upsert_alert(self, value: dict[str, Any]) -> None:
        self._upsert_payload("alert", value["fingerprint"], value)

    def mark_alert_inactive(self, fingerprint: str, resolved_at: str) -> None:
        value = self.get_alert(fingerprint)
        if value is None:
            return
        value["active"] = False
        value["resolvedAt"] = resolved_at
        self.upsert_alert(value)

    def mark_notified(self, fingerprint: str, notified_at: str) -> None:
        value = self.get_alert(fingerprint)
        if value is None:
            return
        value["lastNotifiedAt"] = notified_at
        value["notificationCount"] = int(value.get("notificationCount", 0)) + 1
        self.upsert_alert(value)

    def acknowledge_alert(self, fingerprint: str, acknowledged_at: str) -> None:
        value = self.get_alert(fingerprint)
        if value is None:
            return
        value["acknowledged"] = True
        value["acknowledgedAt"] = acknowledged_at
        self.upsert_alert(value)

    def record_observation(self, key: str, observed_at: datetime) -> datetime:
        row_key = _row_key(key)
        existing = self._get_payload("observation", row_key)
        if existing is None:
            first_seen = observed_at
        else:
            first_seen = _parse_datetime(existing["firstSeenAt"])
        self._upsert_payload(
            "observation",
            row_key,
            {
                "key": key,
                "firstSeenAt": _iso(first_seen),
                "lastSeenAt": _iso(observed_at),
            },
        )
        return first_seen

    def list_observations(self) -> list[dict[str, Any]]:
        return self._query_payloads("observation")

    def delete_observation(self, key: str) -> None:
        self._table.delete_entity("observation", _row_key(key))

    def record_run(self, run_id: str, report: dict[str, Any]) -> None:
        # Blob Storage is the audit history. Keep only the latest summary in
        # Table Storage so repeated timer runs do not grow state without bound.
        summary = {
            "schemaVersion": report.get("schemaVersion"),
            "runId": report.get("runId"),
            "observedAt": report.get("observedAt"),
            "alertCount": report.get("alertCount"),
            "collection": report.get("collection"),
            "notifications": report.get("notifications"),
            "warnings": report.get("warnings", []),
        }
        self._upsert_payload("run", "latest", summary)

    def _get_payload(self, partition_key: str, row_key: str) -> dict[str, Any] | None:
        try:
            entity = self._table.get_entity(partition_key, row_key)
        except Exception as exc:
            if _is_not_found(exc):
                return None
            raise
        return json.loads(entity["payload"])

    def _query_payloads(self, partition_key: str) -> list[dict[str, Any]]:
        entities = self._table.query_entities(
            query_filter="PartitionKey eq @partition",
            parameters={"partition": partition_key},
        )
        return [json.loads(entity["payload"]) for entity in entities]

    def _upsert_payload(
        self, partition_key: str, row_key: str, payload: dict[str, Any]
    ) -> None:
        self._table.upsert_entity(
            {
                "PartitionKey": partition_key,
                "RowKey": row_key,
                "payload": json.dumps(payload, separators=(",", ":"), default=_json_default),
            }
        )


def _row_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}.")


def _is_not_found(exc: Exception) -> bool:
    return getattr(exc, "status_code", None) == 404 or "ResourceNotFound" in str(exc)
