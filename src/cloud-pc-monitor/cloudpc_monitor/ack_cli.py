"""Controlled Table-only operator interface; actor labels are assertions, not identities."""

import argparse
from datetime import datetime, timezone
import json
import re
from uuid import UUID

from .acknowledgements import StateError, public_alert, parse_stamp, validate_request
from .state import TableStateStore, _validate_history


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise StateError("invalid_request")


def create_store(args):
    # No table creation, credential fallback, interactive login or Graph construction.
    from azure.identity import AzureCliCredential
    return TableStateStore(
        f"https://{args.account_name}.table.core.windows.net",
        AzureCliCredential(tenant_id=args.tenant_id, process_timeout=10), args.table,
        create_table=False)


def main(argv=None, *, store_factory=create_store, clock=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument("--account-name", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--table", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show")
    show.add_argument("--fingerprint", required=True)
    history = sub.add_parser("history")
    history.add_argument("--fingerprint", required=True)
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--cursor")
    ack = sub.add_parser("acknowledge")
    for name in ("fingerprint", "episode", "request-id", "actor", "expires-at"):
        ack.add_argument("--" + name, required=True)
    ack.add_argument("--revision", type=int, required=True)
    code = None
    try:
        args = parser.parse_args(argv)
        now = (clock or (lambda: datetime.now(timezone.utc)))()
        if (not re.fullmatch(r"[a-z0-9]{3,24}", args.account_name)
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{2,62}", args.table)
                or str(UUID(args.tenant_id)) != args.tenant_id):
            raise StateError("invalid_request")
        _validate_history(args.fingerprint, getattr(args, "limit", 20), getattr(args, "cursor", None))
        if args.command == "acknowledge":
            expires = parse_stamp(args.expires_at)
            validate_request(args.fingerprint, args.episode, args.revision, args.request_id,
                             args.actor, expires, now)
            if expires <= now:
                raise StateError("invalid_request")
        store = store_factory(args)
        if args.command == "show":
            value = store.get_alert(args.fingerprint)
            if value is None:
                raise StateError("missing_alert")
            result = public_alert(value, args.fingerprint)
        elif args.command == "history":
            result = store.history(args.fingerprint, limit=args.limit, cursor=args.cursor)
        else:
            result = store.acknowledge_alert(
                args.fingerprint, episode=args.episode, revision=args.revision,
                request_id=args.request_id, actor=args.actor, expires_at=expires, now=now)
    except StateError as exc:
        code = exc.code
    except (ValueError, TypeError):
        code = "invalid_request"
    except Exception:
        code = "state_unavailable"
    if code is not None:
        print(json.dumps({"status": "failed", "code": code}))
        return 1
    print(json.dumps({"status": "complete", "result": result}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
