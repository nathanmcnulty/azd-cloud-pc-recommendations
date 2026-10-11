"""Durable state abstractions with an in-memory test implementation."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from .acknowledgements import AlertState, StateError, public_event


class InMemoryStateStore(AlertState):
    """State store used by deterministic fixture runs and unit tests."""

    def __init__(self) -> None:
        self.alerts: dict[str, dict[str, Any]] = {}
        self.observations: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self._versions = {}
        self._events = {}

    def get_alert(self, fingerprint: str) -> dict[str, Any] | None:
        value = self.alerts.get(fingerprint)
        return deepcopy(value) if value is not None else None

    def list_alerts(self) -> list[dict[str, Any]]:
        return [deepcopy(value) for value in self.alerts.values()]

    def _read_alert(self, fingerprint):
        return self.get_alert(fingerprint), self._versions.get(fingerprint)

    def _commit_alert(self, fingerprint, value, token, event):
        if token != self._versions.get(fingerprint):
            return False
        if event is not None and (fingerprint, event["eventId"]) in self._events:
            return False
        self.alerts[fingerprint] = deepcopy(value)
        self._versions[fingerprint] = (token or 0) + 1
        if event is not None:
            self._events[fingerprint, event["eventId"]] = deepcopy(event)
        return True

    def _read_event(self, fingerprint, event_id):
        value = self._events.get((fingerprint, event_id))
        return public_event(value, fingerprint, event_id) if value is not None else None

    def history(self, fingerprint, *, limit=20, cursor=None):
        _validate_history(fingerprint, limit, cursor)
        rows = sorted((event["eventId"], event) for (fp, _), event in self._events.items()
                      if fp == fingerprint and (cursor is None or event["eventId"] > cursor))
        page = rows[:limit]
        return {"events": [public_event(event, fingerprint) for _, event in page],
                "cursor": page[-1][0] if len(rows) > limit else None}

    def record_observation(self, key: str, observed_at: datetime, *, reset_after: datetime | None = None) -> datetime:
        existing = self.observations.get(key)
        if existing is None:
            self.observations[key] = {
                "key": key,
                "firstSeenAt": observed_at,
                "lastSeenAt": observed_at,
            }
            return observed_at
        if reset_after is not None and existing["firstSeenAt"] <= reset_after:
            existing["firstSeenAt"] = observed_at
        existing["lastSeenAt"] = observed_at
        return existing["firstSeenAt"]

    def list_observations(self) -> list[dict[str, Any]]:
        return [deepcopy(value) for value in self.observations.values()]

    def delete_observation(self, key: str) -> None:
        self.observations.pop(key, None)

    def record_run(self, run_id: str, report: dict[str, Any]) -> None:
        self.runs[run_id] = deepcopy(report)


class TableStateStore(AlertState):
    """Azure Table Storage implementation scoped to one dedicated table."""

    def __init__(self, endpoint: str, credential: Any, table_name: str, *,
                 client=None, create_table=True) -> None:
        from azure.data.tables import TableClient

        self._table = client or TableClient(
            endpoint=endpoint,
            credential=credential,
            table_name=table_name,
            retry_total=0,
        )
        if create_table:
            self._table.create_table_if_not_exists()

    def get_alert(self, fingerprint: str) -> dict[str, Any] | None:
        return self._read_alert(fingerprint)[0]

    def list_alerts(self) -> list[dict[str, Any]]:
        return self._query_payloads("alert")

    def _read_alert(self, fingerprint):
        try:
            entity = self._table.get_entity("alert", fingerprint)
            value, etag = json.loads(entity["payload"]), entity.metadata["etag"]
            if (not isinstance(etag, str) or not etag or etag == "*"
                    or not isinstance(value, dict) or value.get("fingerprint") != fingerprint):
                raise StateError("invalid_state")
            return value, etag
        except Exception as exc:
            missing = getattr(exc, "status_code", None) == 404
        if missing:
            return None, None
        raise StateError("state_unavailable") from None

    def _commit_alert(self, fingerprint, value, token, event):
        from azure.core import MatchConditions
        from azure.data.tables import UpdateMode
        entity = _entity("alert", fingerprint, value)
        operation = ("create", entity) if token is None else (
            "update", entity, {"mode": UpdateMode.REPLACE, "etag": token,
                               "match_condition": MatchConditions.IfNotModified})
        try:
            if event is not None:
                self._table.submit_transaction([
                    operation, ("create", _entity("alert", _event_key(fingerprint, event["eventId"]), event))],
                    retry_total=0)
            elif token is None:
                self._table.create_entity(entity, retry_total=0)
            else:
                self._table.update_entity(entity, mode=UpdateMode.REPLACE, etag=token,
                                          match_condition=MatchConditions.IfNotModified, retry_total=0)
            return True
        except Exception as exc:
            conflict = getattr(exc, "status_code", None) in (409, 412)
        if conflict:
            return False
        raise StateError("outcome_unknown") from None

    def _read_event(self, fingerprint, event_id):
        try:
            entity = self._table.get_entity("alert", _event_key(fingerprint, event_id))
            return public_event(json.loads(entity["payload"]), fingerprint, event_id)
        except Exception as exc:
            missing = getattr(exc, "status_code", None) == 404
        if missing:
            return None
        raise StateError("state_unavailable") from None

    def history(self, fingerprint, *, limit=20, cursor=None):
        _validate_history(fingerprint, limit, cursor)
        prefix = "audit:" + fingerprint + ":"
        lower = prefix + (cursor or "")
        try:
            rows = self._table.query_entities(
                query_filter="PartitionKey eq @partition and RowKey gt @lower and RowKey lt @upper",
                parameters={"partition": "alert", "lower": lower, "upper": prefix + "~"},
                results_per_page=limit + 1)
            from itertools import islice
            page = list(islice(rows, limit + 1))
            events = [public_event(json.loads(row["payload"]), fingerprint,
                                   row["RowKey"].removeprefix(prefix)) for row in page[:limit]]
            return {"events": events, "cursor": events[-1]["eventId"] if len(page) > limit else None}
        except Exception:
            pass
        raise StateError("state_unavailable") from None

    def record_observation(self, key: str, observed_at: datetime, *, reset_after: datetime | None = None) -> datetime:
        row_key = _row_key(key)
        existing = self._get_payload("observation", row_key)
        if existing is None:
            first_seen = observed_at
        else:
            first_seen = _parse_datetime(existing["firstSeenAt"])
            if reset_after is not None and first_seen <= reset_after:
                first_seen = observed_at
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
        return [json.loads(entity["payload"]) for entity in entities
                if partition_key != "alert" or not entity["RowKey"].startswith("audit:")]

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


def _entity(partition, key, value):
    return {"PartitionKey": partition, "RowKey": key,
            "payload": json.dumps(value, separators=(",", ":"), default=_json_default)}


def _event_key(fingerprint, event_id):
    return "audit:" + fingerprint + ":" + event_id


def _validate_history(fingerprint, limit, cursor):
    import re
    if (not isinstance(fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", fingerprint)
            or type(limit) is not int or not 1 <= limit <= 100
            or (cursor is not None and (not isinstance(cursor, str)
                or not re.fullmatch(r"[a-f0-9-]{36}|[a-f0-9]{64}", cursor)))):
        raise StateError("invalid_request")
