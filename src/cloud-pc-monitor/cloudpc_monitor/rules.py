"""Cloud PC normalization and the first milestone alert rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any, Iterable, Mapping

from .config import RuleConfig
from .graph_client import GraphSnapshot


@dataclass(frozen=True)
class Alert:
    """An actionable, deduplicated alert."""

    fingerprint: str
    rule_id: str
    severity: str
    route: str
    cloud_pc_id: str
    title: str
    summary: str
    first_seen_at: datetime
    detected_at: datetime
    action_url: str
    evidence: dict[str, Any]

    def as_payload(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "ruleId": self.rule_id,
            "severity": self.severity,
            "route": self.route,
            "cloudPcId": self.cloud_pc_id,
            "title": self.title,
            "summary": self.summary,
            "firstSeenAt": isoformat(self.first_seen_at),
            "detectedAt": isoformat(self.detected_at),
            "actionUrl": self.action_url,
            "evidence": self.evidence,
        }

    def as_state(self, existing: Mapping[str, Any] | None = None) -> dict[str, Any]:
        previous = existing or {}
        return {
            **self.as_payload(),
            "active": True,
            "acknowledged": bool(previous.get("acknowledged", False)),
            "acknowledgedAt": previous.get("acknowledgedAt"),
            "lastNotifiedAt": previous.get("lastNotifiedAt"),
            "notificationCount": int(previous.get("notificationCount", 0)),
        }


def normalize_records(
    snapshot: GraphSnapshot, *, action_url: str = ""
) -> list[dict[str, Any]]:
    """Join Cloud PC, managed-device, and recommendation rows."""

    managed_by_id = {
        str(item.get("id")): item
        for item in snapshot.managed_devices
        if item.get("id")
    }
    recommendations_by_id = {
        _value(item, "CloudPcId", "cloudPcId"): item
        for item in snapshot.recommendations
        if _value(item, "CloudPcId", "cloudPcId")
    }

    records: list[dict[str, Any]] = []
    for cloud_pc in snapshot.cloud_pcs:
        cloud_pc_id = str(cloud_pc.get("id", "")).strip()
        if not cloud_pc_id:
            continue
        managed_device_id = _string(cloud_pc.get("managedDeviceId"))
        managed = managed_by_id.get(managed_device_id or "", {})
        recommendation = recommendations_by_id.get(cloud_pc_id, {})
        status_detail = cloud_pc.get("statusDetail") or cloud_pc.get("statusDetails") or {}
        connectivity = cloud_pc.get("connectivityResult") or {}
        last_login_result = cloud_pc.get("lastLoginResult") or {}
        last_login_at = parse_datetime(
            _value(last_login_result, "time", "Time", "dateTime")
        )
        last_sync_at = parse_datetime(managed.get("lastSyncDateTime"))
        records.append(
            {
                "id": cloud_pc_id,
                "display_name": _string(cloud_pc.get("displayName")) or cloud_pc_id,
                "user_principal_name": _string(
                    cloud_pc.get("userPrincipalName")
                    or managed.get("userPrincipalName")
                ),
                "status": _lower(cloud_pc.get("status")),
                "status_detail_code": _string(
                    _value(status_detail, "code", "Code")
                ),
                "status_detail_message": _string(
                    _value(status_detail, "message", "Message")
                ),
                "connectivity_status": _lower(
                    _value(connectivity, "status", "Status")
                ),
                "managed_device_id": managed_device_id,
                "managed_device_name": _string(
                    cloud_pc.get("managedDeviceName") or managed.get("deviceName")
                ),
                "last_login_at": last_login_at,
                "last_logoff_at": parse_datetime(cloud_pc.get("lastLogoffDateTime")),
                "last_sync_at": last_sync_at,
                "compliance_state": _lower(managed.get("complianceState")),
                "management_state": _lower(managed.get("managementState")),
                "provisioned_at": parse_datetime(cloud_pc.get("provisionedDateTime")),
                "last_modified_at": parse_datetime(
                    cloud_pc.get("lastModifiedDateTime")
                ),
                "recommendation_usage_insight": _lower(
                    _value(recommendation, "UsageInsight", "usageInsight")
                ),
                "recommendation_plan_name": _string(
                    _value(recommendation, "RecommendedPlanName", "recommendedPlanName")
                ),
                "action_url": action_url,
            }
        )
    return records


def evaluate_alerts(
    records: Iterable[Mapping[str, Any]],
    rules: Iterable[RuleConfig],
    state: Any,
    *,
    now: datetime | None = None,
    global_suppressions: frozenset[str] = frozenset(),
) -> list[Alert]:
    """Evaluate rules and synchronize durable alert and grace-period state."""

    observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    current_fingerprints: set[str] = set()
    candidate_keys: set[str] = set()
    alerts: list[Alert] = []

    for record in records:
        cloud_pc_id = str(record.get("id", ""))
        user = str(record.get("user_principal_name", ""))
        if not cloud_pc_id:
            continue
        for rule in rules:
            if not rule.enabled or rule.id in global_suppressions:
                continue
            if cloud_pc_id in rule.suppressed_cloud_pc_ids or user in rule.suppressed_users:
                continue

            reason = _rule_reason(rule, record, observed_at)
            observation_key = f"{rule.id}:{cloud_pc_id}"
            if reason is None:
                state.delete_observation(observation_key)
                continue

            candidate_keys.add(observation_key)
            first_seen = state.record_observation(observation_key, observed_at)
            fingerprint = fingerprint_for(rule.id, cloud_pc_id)
            current_fingerprints.add(fingerprint)
            elapsed_minutes = max(
                0.0, (observed_at - first_seen).total_seconds() / 60.0
            )
            if elapsed_minutes < rule.grace_period_minutes:
                continue

            alert = Alert(
                fingerprint=fingerprint,
                rule_id=rule.id,
                severity=rule.severity,
                route=rule.route,
                cloud_pc_id=cloud_pc_id,
                title=_title(rule.id, record),
                summary=reason,
                first_seen_at=first_seen,
                detected_at=observed_at,
                action_url=str(record.get("action_url", "")),
                evidence=_evidence(record),
            )
            alerts.append(alert)
            existing = state.get_alert(fingerprint)
            state.upsert_alert(alert.as_state(existing))

    for observation in state.list_observations():
        key = str(observation.get("key", ""))
        if key and key not in candidate_keys:
            state.delete_observation(key)

    resolved_at = isoformat(observed_at)
    for existing in state.list_alerts():
        fingerprint = existing.get("fingerprint")
        if (
            existing.get("active", False)
            and fingerprint
            and fingerprint not in current_fingerprints
        ):
            state.mark_alert_inactive(str(fingerprint), resolved_at)

    return alerts


def fingerprint_for(rule_id: str, cloud_pc_id: str) -> str:
    """Return a stable fingerprint that is independent of changing evidence text."""

    return hashlib.sha256(f"{rule_id}:{cloud_pc_id}".encode("utf-8")).hexdigest()


def parse_datetime(value: Any) -> datetime | None:
    """Parse Graph timestamps and the nested last-login timestamp."""

    if isinstance(value, dict):
        value = _value(value, "time", "Time", "dateTime")
    if value is None or not str(value).strip():
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _rule_reason(
    rule: RuleConfig, record: Mapping[str, Any], now: datetime
) -> str | None:
    if rule.id == "unused-cloud-pc":
        if record.get("recommendation_usage_insight") in {
            "underutilized",
            "unused",
            "neverused",
            "no usage",
            "noactivity",
        }:
            return "Microsoft Graph reported the Cloud PC as underutilized or unused."
        last_login = record.get("last_login_at")
        if isinstance(last_login, datetime):
            age_days = _age_days(last_login, now)
            if age_days >= rule.threshold_days:
                return (
                    f"No Cloud PC login was observed for approximately {age_days:.0f} days "
                    f"(threshold {rule.threshold_days} days)."
                )
        else:
            provisioned_at = record.get("provisioned_at")
            if isinstance(provisioned_at, datetime):
                age_days = _age_days(provisioned_at, now)
                if age_days >= rule.threshold_days:
                    return (
                        "No Cloud PC login was observed since provisioning "
                        f"approximately {age_days:.0f} days ago "
                        f"(threshold {rule.threshold_days} days)."
                    )
        return None

    if rule.id == "provisioning-failure":
        if record.get("status") == "failed":
            detail = record.get("status_detail_message") or record.get(
                "status_detail_code"
            )
            return (
                "Cloud PC provisioning or the latest Cloud PC operation failed"
                + (f": {detail}." if detail else ".")
            )
        return None

    if rule.id == "unhealthy-stale-device":
        if record.get("status") == "provisionedwithwarnings":
            return "Cloud PC is provisioned with warnings."
        if record.get("connectivity_status") in {
            "unavailable",
            "underservicemaintenance",
        }:
            return "Cloud PC connectivity health is unavailable or under service maintenance."
        if record.get("management_state") == "unhealthy":
            return "The Intune managed device reports an unhealthy management state."
        if record.get("compliance_state") in {"noncompliant", "conflict", "error"}:
            return (
                "The Intune managed device reports a "
                f"{record['compliance_state']} compliance state."
            )
        last_sync = record.get("last_sync_at")
        if isinstance(last_sync, datetime):
            age_days = _age_days(last_sync, now)
            if age_days >= rule.threshold_days:
                return (
                    f"The Intune managed device has not synced for approximately {age_days:.0f} days "
                    f"(threshold {rule.threshold_days} days)."
                )
        return None

    return None


def _title(rule_id: str, record: Mapping[str, Any]) -> str:
    display_name = record.get("display_name") or record.get("id")
    titles = {
        "unused-cloud-pc": "Unused Cloud PC requires review",
        "provisioning-failure": "Cloud PC provisioning failure requires review",
        "unhealthy-stale-device": "Cloud PC device health requires review",
    }
    return f"{titles.get(rule_id, 'Cloud PC alert')}: {display_name}"


def _evidence(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "displayName": record.get("display_name"),
        "userPrincipalName": record.get("user_principal_name"),
        "status": record.get("status"),
        "connectivityStatus": record.get("connectivity_status"),
        "complianceState": record.get("compliance_state"),
        "managementState": record.get("management_state"),
        "lastLoginAt": _optional_iso(record.get("last_login_at")),
        "lastSyncAt": _optional_iso(record.get("last_sync_at")),
        "recommendationUsageInsight": record.get("recommendation_usage_insight"),
        "recommendedPlanName": record.get("recommendation_plan_name"),
        "statusDetailCode": record.get("status_detail_code"),
    }


def _optional_iso(value: Any) -> str | None:
    return isoformat(value) if isinstance(value, datetime) else None


def _age_days(timestamp: datetime, now: datetime) -> float:
    return max(0.0, (now - timestamp).total_seconds() / 86400.0)


def _value(mapping: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    lowered = {str(key).lower(): value for key, value in mapping.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _string(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _lower(value: Any) -> str:
    return _string(value).lower()
