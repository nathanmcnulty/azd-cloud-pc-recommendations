"""Exact alert acknowledgement transitions; no collection or delivery authority."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import re
from uuid import UUID, uuid4


class StateError(Exception):
    """Closed diagnostic suitable for operator output."""

    CODES = frozenset({"invalid_request", "missing_alert", "inactive_alert",
                       "stale_identity", "request_reused", "state_conflict",
                       "state_unavailable", "outcome_unknown", "invalid_state"})

    def __init__(self, code):
        self.code = code if code in self.CODES else "state_unavailable"
        super().__init__(self.code)


def utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise StateError("invalid_request")
    return value.astimezone(timezone.utc)


def stamp(value):
    return utc(value).isoformat().replace("+00:00", "Z")


def parse_stamp(value):
    try:
        return utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (AttributeError, TypeError, ValueError):
        pass
    raise StateError("invalid_state")


def validate_request(fingerprint, episode, revision, request_id, actor, expires_at, now):
    if (not isinstance(fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", fingerprint)
            or not isinstance(episode, str) or not re.fullmatch(r"[a-f0-9]{64}", episode)
            or type(revision) is not int or revision < 0
            or not isinstance(actor, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}", actor)):
        raise StateError("invalid_request")
    try:
        if not isinstance(request_id, str) or str(UUID(request_id)) != request_id:
            raise ValueError()
    except (ValueError, AttributeError):
        raise StateError("invalid_request") from None
    utc(now)
    return {"fingerprint": fingerprint, "episode": episode, "expectedRevision": revision,
            "requestId": request_id, "actor": actor, "actorSource": "operator_asserted",
            "expiresAt": stamp(expires_at)}


def identity(value):
    """Legacy episode is stable, and does not assert legacy actor authenticity."""
    result = deepcopy(value)
    if (not isinstance(result.get("fingerprint"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", result["fingerprint"])):
        raise StateError("invalid_state")
    if "episode" not in result:
        if not isinstance(result.get("firstSeenAt"), str):
            raise StateError("invalid_state")
        result["episode"] = hashlib.sha256(
            (result["fingerprint"] + ":" + result["firstSeenAt"]).encode()).hexdigest()
        result["ackRevision"] = 0
    if (not isinstance(result["episode"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", result["episode"])
            or type(result.get("ackRevision")) is not int or result["ackRevision"] < 0
            or type(result.get("active")) is not bool
            or type(result.get("acknowledged", False)) is not bool):
        raise StateError("invalid_state")
    return result


def effective_acknowledgement(value, now):
    if not value or not value.get("acknowledged", False):
        return False
    # Historical indefinite acknowledgements remain suppressed, with unknown provenance.
    expiry = value.get("ackExpiresAt")
    return expiry is None or utc(now) < parse_stamp(expiry)


def health_time(value):
    """Only health observations/resolutions establish ordering, never operator time."""
    detected = parse_stamp(value.get("detectedAt"))
    if type(value.get("active")) is not bool:
        raise StateError("invalid_state")
    resolved = parse_stamp(value["resolvedAt"]) if "resolvedAt" in value else None
    if not value["active"] and (resolved is None or resolved < detected):
        raise StateError("invalid_state")
    if value["active"] and resolved is not None and resolved >= detected:
        raise StateError("invalid_state")
    return max(detected, resolved) if resolved is not None else detected


def delivery_is_current(alert, value):
    if not value or value.get("active") is not True:
        return False
    if alert.episode != value.get("episode"):
        return False
    return health_time(value) == utc(alert.detected_at)


def public_alert(value, fingerprint):
    result = identity(value)
    if result["fingerprint"] != fingerprint:
        raise StateError("invalid_state")
    output = {key: result.get(key) for key in (
        "fingerprint", "episode", "ackRevision", "active", "acknowledged")}
    for key in ("acknowledgedAt", "ackExpiresAt"):
        output[key] = stamp(parse_stamp(result[key])) if result.get(key) is not None else None
    actor = result.get("ackActor")
    if actor is not None and (not isinstance(actor, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}", actor)):
        raise StateError("invalid_state")
    output["ackActor"] = actor
    source = result.get("ackActorSource")
    if source not in (None, "operator_asserted") or (source == "operator_asserted" and actor is None):
        raise StateError("invalid_state")
    output["ackActorSource"] = source or ("legacy_unknown" if result.get("acknowledged") else None)
    return output


def public_event(value, fingerprint, event_id=None):
    if (not isinstance(value, dict) or value.get("fingerprint") != fingerprint
            or value.get("kind") not in ("acknowledged", "expired", "resolved", "reopened")
            or not isinstance(value.get("episode"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", value["episode"])
            or type(value.get("revision")) is not int or value["revision"] < 0
            or not isinstance(value.get("eventId"), str)
            or not re.fullmatch(r"[a-f0-9-]{36}|[a-f0-9]{64}", value["eventId"])
            or (event_id is not None and value["eventId"] != event_id)):
        raise StateError("invalid_state")
    result = {key: value[key] for key in ("fingerprint", "episode", "revision", "eventId", "kind")}
    result["recordedAt"] = stamp(parse_stamp(value.get("recordedAt")))
    if value["kind"] == "acknowledged":
        request = value.get("request")
        if not isinstance(request, dict):
            raise StateError("invalid_state")
        result["request"] = validate_request(fingerprint, value["episode"],
            request.get("expectedRevision"), request.get("requestId"), request.get("actor"),
            parse_stamp(request.get("expiresAt")), parse_stamp(value["recordedAt"]))
        if (request.get("fingerprint") != fingerprint or request.get("episode") != value["episode"]
                or request.get("requestId") != value["eventId"]
                or request.get("actorSource") != "operator_asserted"
                or value["revision"] != request.get("expectedRevision", -1) + 1
                or parse_stamp(request.get("expiresAt")) <= parse_stamp(value["recordedAt"])):
            raise StateError("invalid_state")
    return result


class AlertState:
    """Both storage backends execute these identical bounded CAS transitions."""

    def _change(self, fingerprint, transition):
        for _ in range(4):
            value, token = self._read_alert(fingerprint)
            if value is not None and (not isinstance(value, dict) or value.get("fingerprint") != fingerprint):
                raise StateError("invalid_state")
            updated, event = transition(deepcopy(value))
            if updated is None:
                return value
            if self._commit_alert(fingerprint, updated, token, event):
                return updated
        raise StateError("state_conflict")

    def upsert_alert(self, value):
        # Compatibility with existing callers, but preserve concurrent metadata.
        return self._change(value["fingerprint"], lambda old: ({**(old or {}), **value}, None))

    def synchronize_alert(self, payload, now):
        observed_at = utc(now)
        if parse_stamp(payload.get("detectedAt")) != observed_at:
            raise StateError("invalid_state")
        def change(old):
            event = None
            if old is None:
                updated = identity({**payload, "active": True, "acknowledged": False,
                                    "notificationCount": 0, "lastNotifiedAt": None})
            else:
                updated = identity(old)
                latest = health_time(updated)
                if observed_at < latest or (observed_at == latest and (
                        not updated["active"] or any(updated.get(key) != value for key, value in payload.items()))):
                    return None, None
                if not updated["active"]:
                    updated["episode"] = hashlib.sha256(str(uuid4()).encode()).hexdigest()
                    updated["ackRevision"] += 1
                    updated["acknowledged"] = False
                    for key in ("acknowledgedAt", "ackExpiresAt", "ackActor", "ackActorSource", "ackRequestId"):
                        updated.pop(key, None)
                    event = self._event(updated, "reopened", now)
                elif updated.get("acknowledged") and not effective_acknowledgement(updated, now):
                    updated["acknowledged"] = False
                    updated["ackRevision"] += 1
                    event = self._event(updated, "expired", now)
                updated.update(payload)
                updated["active"] = True
            return updated, event
        value = self._change(payload["fingerprint"], change)
        if (value is not None and value.get("active") is True and health_time(value) == observed_at
                and all(value.get(key) == item for key, item in payload.items())):
            return value
        return None

    def mark_alert_inactive(self, fingerprint, resolved_at, *, episode=None):
        observed_at = parse_stamp(resolved_at)
        if episode is None:
            captured = self.get_alert(fingerprint)
            if captured is None:
                return None
            episode = identity(captured)["episode"]
        def change(old):
            if old is None or not old.get("active"):
                return None, None
            updated = identity(old)
            if updated["episode"] != episode or observed_at <= health_time(updated):
                return None, None
            updated.update(active=False, resolvedAt=resolved_at)
            return updated, self._event(updated, "resolved", parse_stamp(resolved_at))
        return self._change(fingerprint, change)

    def mark_notified(self, fingerprint, notified_at, *, episode=None):
        successful_at = parse_stamp(notified_at)
        def change(old):
            if old is None:
                return None, None
            if episode is not None and old.get("episode") != episode:
                return None, None
            previous_at = old.get("lastNotifiedAt")
            latest = max(parse_stamp(previous_at), successful_at) if previous_at is not None else successful_at
            old["lastNotifiedAt"] = stamp(latest)
            old["notificationCount"] = int(old.get("notificationCount", 0)) + 1
            return old, None
        return self._change(fingerprint, change)

    @staticmethod
    def _event(value, kind, now):
        event_id = hashlib.sha256(
            f"{value['episode']}:{kind}:{value['ackRevision']}".encode()).hexdigest()
        return {"eventId": event_id, "fingerprint": value["fingerprint"],
                "episode": value["episode"], "revision": value["ackRevision"],
                "kind": kind, "recordedAt": stamp(now)}

    def acknowledge_alert(self, fingerprint, *, episode, revision, request_id,
                          actor, expires_at, now):
        request = validate_request(fingerprint, episode, revision, request_id, actor, expires_at, now)
        event_id = request_id
        previous = self._read_event(fingerprint, event_id)
        if previous is not None:
            previous = public_event(previous, fingerprint, event_id)
            if previous.get("request") != request:
                raise StateError("request_reused")
            return previous
        if utc(expires_at) <= utc(now):
            raise StateError("invalid_request")
        expected_event = {"eventId": event_id, "fingerprint": fingerprint, "episode": episode,
                          "revision": revision + 1, "kind": "acknowledged", "recordedAt": stamp(now),
                          "request": request}
        def change(old):
            if old is None:
                raise StateError("missing_alert")
            updated = identity(old)
            if not updated["active"]:
                raise StateError("inactive_alert")
            if updated["episode"] != episode or updated["ackRevision"] != revision:
                raise StateError("stale_identity")
            updated.update(acknowledged=True, acknowledgedAt=stamp(now),
                           ackExpiresAt=stamp(expires_at), ackActor=actor,
                           ackActorSource="operator_asserted", ackRequestId=request_id,
                           ackRevision=revision + 1)
            return updated, deepcopy(expected_event)
        try:
            self._change(fingerprint, change)
        except StateError as exc:
            code = exc.code
        else:
            previous = self._read_event(fingerprint, event_id)
            if previous is None:
                raise StateError("outcome_unknown")
            previous = public_event(previous, fingerprint, event_id)
            if previous != expected_event:
                raise StateError("outcome_unknown")
            return previous
        # A failed acknowledgement is never blindly repeated. Resolve only its exact event.
        previous = self._read_event(fingerprint, event_id)
        if previous is not None:
            previous = public_event(previous, fingerprint, event_id)
            if previous.get("request") != request:
                raise StateError("request_reused")
            return previous
        raise StateError(code) from None
