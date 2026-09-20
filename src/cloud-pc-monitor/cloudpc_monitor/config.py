"""Environment-backed configuration and rule definitions."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Mapping


class ConfigurationError(ValueError):
    """Raised when an operator supplied configuration is invalid."""


@dataclass(frozen=True)
class RuleConfig:
    """A configurable alert rule."""

    id: str
    enabled: bool
    severity: str
    threshold_days: int
    grace_period_minutes: int
    route: str
    suppressed_cloud_pc_ids: frozenset[str]
    suppressed_users: frozenset[str]


@dataclass(frozen=True)
class Settings:
    """Runtime settings for a monitor invocation."""

    graph_api_version: str
    recommendations_enabled: bool
    dry_run: bool
    notifications_enabled: bool
    send_notifications_in_dry_run: bool
    teams_webhook_url: str
    storage_account_url: str
    report_container_name: str
    state_table_name: str
    intune_cloud_pc_url: str
    unused_cloud_pc_days: int
    stale_device_days: int
    provisioning_failure_grace_minutes: int
    unhealthy_device_grace_minutes: int
    notification_renotify_hours: int
    graph_page_size: int
    max_retries: int
    rules: tuple[RuleConfig, ...]
    global_suppressions: frozenset[str]

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str] | None = None
    ) -> "Settings":
        values = os.environ if environ is None else environ
        unused_days = _positive_int(values, "UNUSED_CLOUD_PC_DAYS", 30)
        stale_days = _positive_int(values, "STALE_DEVICE_DAYS", 14)
        provisioning_grace = _non_negative_int(
            values, "PROVISIONING_FAILURE_GRACE_MINUTES", 60
        )
        unhealthy_grace = _non_negative_int(
            values, "UNHEALTHY_DEVICE_GRACE_MINUTES", 60
        )

        graph_api_version = values.get("GRAPH_API_VERSION", "beta").strip()
        if graph_api_version not in {"v1.0", "beta"}:
            raise ConfigurationError(
                "GRAPH_API_VERSION must be either 'v1.0' or 'beta'."
            )

        return cls(
            graph_api_version=graph_api_version,
            recommendations_enabled=_boolean(
                values, "CLOUD_PC_RECOMMENDATIONS_ENABLED", False
            ),
            dry_run=_boolean(values, "DRY_RUN", True),
            notifications_enabled=_boolean(
                values, "NOTIFICATIONS_ENABLED", True
            ),
            send_notifications_in_dry_run=_boolean(
                values, "SEND_NOTIFICATIONS_IN_DRY_RUN", False
            ),
            teams_webhook_url=values.get("TEAMS_WEBHOOK_URL", "").strip(),
            storage_account_url=values.get("STORAGE_ACCOUNT_URL", "").strip(),
            report_container_name=values.get(
                "REPORT_CONTAINER_NAME", "reports"
            ).strip(),
            state_table_name=values.get("STATE_TABLE_NAME", "CloudPcState").strip(),
            intune_cloud_pc_url=values.get(
                "INTUNE_CLOUD_PC_URL", "https://intune.microsoft.com/"
            ).strip(),
            unused_cloud_pc_days=unused_days,
            stale_device_days=stale_days,
            provisioning_failure_grace_minutes=provisioning_grace,
            unhealthy_device_grace_minutes=unhealthy_grace,
            notification_renotify_hours=_non_negative_int(
                values, "NOTIFICATION_RENOTIFY_HOURS", 24
            ),
            graph_page_size=_bounded_int(values, "GRAPH_PAGE_SIZE", 100, 1, 999),
            max_retries=_bounded_int(values, "GRAPH_MAX_RETRIES", 4, 0, 8),
            rules=load_rules(
                values,
                unused_days=unused_days,
                stale_days=stale_days,
                provisioning_grace=provisioning_grace,
                unhealthy_grace=unhealthy_grace,
            ),
            global_suppressions=frozenset(
                item.strip()
                for item in values.get("ALERT_SUPPRESSIONS", "").split(",")
                if item.strip()
            ),
        )


_DEFAULT_RULES = (
    {
        "id": "unused-cloud-pc",
        "enabled": True,
        "severity": "medium",
        "thresholdDays": 30,
        "gracePeriodMinutes": 0,
        "route": "cloud-pc-operations",
    },
    {
        "id": "provisioning-failure",
        "enabled": True,
        "severity": "high",
        "thresholdDays": 0,
        "gracePeriodMinutes": 60,
        "route": "cloud-pc-operations",
    },
    {
        "id": "unhealthy-stale-device",
        "enabled": True,
        "severity": "high",
        "thresholdDays": 14,
        "gracePeriodMinutes": 60,
        "route": "cloud-pc-operations",
    },
)


def load_rules(
    environ: Mapping[str, str],
    *,
    unused_days: int,
    stale_days: int,
    provisioning_grace: int,
    unhealthy_grace: int,
) -> tuple[RuleConfig, ...]:
    """Load the built-in rules or a complete operator-supplied JSON array."""

    raw = environ.get("CLOUD_PC_RULES_JSON", "").strip()
    if raw:
        try:
            definitions = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConfigurationError(
                "CLOUD_PC_RULES_JSON must contain a valid JSON array."
            ) from exc
        if not isinstance(definitions, list):
            raise ConfigurationError("CLOUD_PC_RULES_JSON must be a JSON array.")
    else:
        definitions = [dict(item) for item in _DEFAULT_RULES]

    defaults = {
        "unused-cloud-pc": (unused_days, 0),
        "provisioning-failure": (0, provisioning_grace),
        "unhealthy-stale-device": (stale_days, unhealthy_grace),
    }
    rules: list[RuleConfig] = []
    seen: set[str] = set()
    for index, definition in enumerate(definitions):
        if not isinstance(definition, dict):
            raise ConfigurationError(f"Rule at index {index} must be an object.")

        rule_id = str(definition.get("id", "")).strip()
        if not rule_id or rule_id in seen:
            raise ConfigurationError(
                f"Rule at index {index} must have a unique non-empty id."
            )
        seen.add(rule_id)

        default_threshold, default_grace = defaults.get(rule_id, (0, 0))
        threshold_days = _mapping_int(
            definition, "thresholdDays", default_threshold, minimum=0
        )
        grace_minutes = _mapping_int(
            definition, "gracePeriodMinutes", default_grace, minimum=0
        )
        severity = str(definition.get("severity", "medium")).strip().lower()
        if severity not in {"low", "medium", "high", "critical"}:
            raise ConfigurationError(
                f"Rule '{rule_id}' severity must be low, medium, high, or critical."
            )
        route = str(definition.get("route", "cloud-pc-operations")).strip()
        if not route:
            raise ConfigurationError(f"Rule '{rule_id}' route cannot be empty.")

        suppression = definition.get("suppression", {})
        if not isinstance(suppression, dict):
            raise ConfigurationError(
                f"Rule '{rule_id}' suppression must be an object."
            )

        rules.append(
            RuleConfig(
                id=rule_id,
                enabled=_mapping_bool(definition, "enabled", True),
                severity=severity,
                threshold_days=threshold_days,
                grace_period_minutes=grace_minutes,
                route=route,
                suppressed_cloud_pc_ids=_string_set(
                    suppression.get("cloudPcIds", [])
                ),
                suppressed_users=_string_set(
                    suppression.get("userPrincipalNames", [])
                ),
            )
        )

    if not rules:
        raise ConfigurationError("At least one alert rule must be configured.")
    return tuple(rules)


def _string_set(value: object) -> frozenset[str]:
    if value is None:
        return frozenset()
    if not isinstance(value, (list, tuple, set)):
        raise ConfigurationError("Suppression values must be arrays of strings.")
    return frozenset(str(item).strip() for item in value if str(item).strip())


def _mapping_bool(mapping: Mapping[str, object], name: str, default: bool) -> bool:
    value = mapping.get(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _parse_bool(value, name)
    raise ConfigurationError(f"Rule property '{name}' must be a boolean.")


def _mapping_int(
    mapping: Mapping[str, object],
    name: str,
    default: int,
    *,
    minimum: int,
) -> int:
    value = mapping.get(name, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"Rule property '{name}' must be an integer.") from exc
    if parsed < minimum:
        raise ConfigurationError(
            f"Rule property '{name}' must be at least {minimum}."
        )
    return parsed


def _boolean(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name)
    if raw is None or not str(raw).strip():
        return default
    return _parse_bool(str(raw), name)


def _parse_bool(raw: str, name: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be a boolean value.")


def _positive_int(values: Mapping[str, str], name: str, default: int) -> int:
    return _bounded_int(values, name, default, 1, 3650)


def _non_negative_int(values: Mapping[str, str], name: str, default: int) -> int:
    return _bounded_int(values, name, default, 0, 525600)


def _bounded_int(
    values: Mapping[str, str], name: str, default: int, minimum: int, maximum: int
) -> int:
    raw = values.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        parsed = int(str(raw).strip())
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if parsed < minimum or parsed > maximum:
        raise ConfigurationError(
            f"{name} must be between {minimum} and {maximum}."
        )
    return parsed
