"""Teams Workflows webhook delivery with alert deduplication."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import time
from typing import Any, Callable, Iterable

try:
    import requests
except ImportError:  # pragma: no cover - the deployed app declares requests
    requests = None  # type: ignore[assignment]

from .config import Settings
from .rules import Alert, parse_datetime


class NotificationError(RuntimeError):
    """A Teams webhook request failed."""


class TeamsNotifier:
    """Send Adaptive Cards to a Teams Workflows webhook."""

    def __init__(
        self,
        settings: Settings,
        *,
        session: Any | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self.session = session
        if self.session is None and self._may_send():
            self.session = _new_requests_session()
        self.sleeper = sleeper

    def _may_send(self) -> bool:
        return bool(
            self.settings.notifications_enabled
            and self.settings.teams_webhook_url
            and (
                not self.settings.dry_run
                or self.settings.send_notifications_in_dry_run
            )
        )

    def deliver(
        self,
        alerts: Iterable[Alert],
        state: Any,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Send only new or due alerts and update notification history on success."""

        observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        candidates = list(alerts)
        due = [
            alert
            for alert in candidates
            if self._is_due(alert, state, observed_at)
        ]
        if not due:
            return {
                "status": "none",
                "candidateCount": len(candidates),
                "sentCount": 0,
                "reason": "deduplicated_or_acknowledged",
            }

        if not self.settings.notifications_enabled:
            return {
                "status": "skipped",
                "candidateCount": len(candidates),
                "sentCount": 0,
                "reason": "notifications_disabled",
            }
        if self.settings.dry_run and not self.settings.send_notifications_in_dry_run:
            return {
                "status": "skipped",
                "candidateCount": len(candidates),
                "sentCount": 0,
                "reason": "dry_run",
            }
        if not self.settings.teams_webhook_url:
            return {
                "status": "skipped",
                "candidateCount": len(candidates),
                "sentCount": 0,
                "reason": "webhook_not_configured",
            }

        sent = 0
        try:
            for chunk in _chunks(due, 10):
                self._send(build_payload(chunk), len(chunk))
                for alert in chunk:
                    state.mark_notified(alert.fingerprint, _iso(observed_at))
                    sent += 1
        except NotificationError as exc:
            logging.error("Teams notification failed after %s alerts: %s", sent, exc)
            return {
                "status": "failed",
                "candidateCount": len(candidates),
                "sentCount": sent,
                "reason": "webhook_request_failed",
            }

        return {
            "status": "sent",
            "candidateCount": len(candidates),
            "sentCount": sent,
            "reason": "new_or_due_alerts",
        }

    def _is_due(self, alert: Alert, state: Any, now: datetime) -> bool:
        previous = state.get_alert(alert.fingerprint)
        if previous and previous.get("acknowledged", False):
            return False
        if not previous:
            return True
        last_notified = parse_datetime(previous.get("lastNotifiedAt"))
        if last_notified is None:
            return True
        elapsed_hours = (now - last_notified).total_seconds() / 3600.0
        return elapsed_hours >= self.settings.notification_renotify_hours

    def _send(self, payload: dict[str, Any], alert_count: int) -> None:
        if self.session is None:
            raise NotificationError("Teams delivery session is not configured.")
        for attempt in range(4):
            response = self.session.post(
                self.settings.teams_webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            if 200 <= response.status_code < 300:
                return
            if response.status_code not in {429, 500, 502, 503, 504} or attempt == 3:
                detail = (getattr(response, "text", "") or "").replace("\n", " ")[:300]
                raise NotificationError(
                    f"Teams webhook returned HTTP {response.status_code} for {alert_count} alerts: {detail}"
                )
            retry_after = _retry_after(response.headers.get("Retry-After"))
            self.sleeper(retry_after if retry_after is not None else min(30.0, 2**attempt))


def build_payload(alerts: Iterable[Alert]) -> dict[str, Any]:
    """Build a Teams Workflows-compatible message with Adaptive Card content."""

    alert_list = list(alerts)
    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": f"Cloud PC operational alerts ({len(alert_list)})",
            "weight": "Bolder",
            "size": "Medium",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": "Review the affected Cloud PCs in Intune. No remediation was performed by this alert.",
            "isSubtle": True,
            "wrap": True,
        },
    ]
    actions: list[dict[str, Any]] = []
    for alert in alert_list:
        evidence = alert.evidence
        facts = [
            {"title": "Severity", "value": alert.severity},
            {"title": "Route", "value": alert.route},
            {"title": "User", "value": evidence.get("userPrincipalName") or "Unassigned"},
        ]
        body.append(
            {
                "type": "Container",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": alert.title,
                        "weight": "Bolder",
                        "wrap": True,
                    },
                    {"type": "TextBlock", "text": alert.summary, "wrap": True},
                    {"type": "FactSet", "facts": facts},
                ],
                "separator": True,
            }
        )
        if alert.action_url:
            actions.append(
                {
                    "type": "Action.OpenUrl",
                    "title": "Open Intune",
                    "url": alert.action_url,
                }
            )

    card: dict[str, Any] = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
    }
    if actions:
        card["actions"] = actions
    return {
        "type": "message",
        "text": "Cloud PC operational alerts require review.",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": card,
            }
        ],
    }


def _chunks(items: list[Alert], size: int) -> Iterable[list[Alert]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _retry_after(raw: Any) -> float | None:
    try:
        return max(0.0, min(float(str(raw)), 120.0))
    except (TypeError, ValueError):
        return None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_requests_session() -> Any:
    if requests is None:
        raise RuntimeError(
            "The requests package is required for live Teams delivery. "
            "Install src/cloud-pc-monitor/requirements.txt."
        )
    return requests.Session()
