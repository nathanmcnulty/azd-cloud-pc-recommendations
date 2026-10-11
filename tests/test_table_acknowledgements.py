"""Real Azure Table SDK over an in-process HTTP transport; no service or credentials."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "cloud-pc-monitor"))
from azure.core.credentials import AzureNamedKeyCredential
from azure.core.exceptions import ServiceResponseError
from azure.core.pipeline.transport import HttpTransport, HttpResponse
from azure.data.tables import TableClient
from cloudpc_monitor.state import TableStateStore
from cloudpc_monitor.acknowledgements import StateError
from tests.test_acknowledgements import NOW, REQUEST, acknowledge, activate


class Response(HttpResponse):
    def __init__(self, request, status, body=None, etag='W/"fixture-1"', parts=None):
        super().__init__(request, None)
        self.status_code = status
        self.headers = {"Content-Type": "application/json", "ETag": etag,
                        "x-ms-version": "2019-02-02"}
        self.content_type = "application/json"
        self._body = json.dumps(body or {}).encode()
        self._parts = parts or []
        self.reason = "fixture"

    def body(self):
        return self._body

    def parts(self):
        return iter(self._parts)

    def stream_download(self, pipeline, **kwargs):
        return iter([self._body])


class WireTransport(HttpTransport):
    def __init__(self):
        self.calls = []
        self.rows = {}
        self.version = 0
        self.conflict = False
        self.lost = False
        self.fail_audit = False
        self.interleave = None
        self.lost_single = False
        self.server_error = False

    def open(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _put(self, entity):
        self.version += 1
        self.rows[entity["PartitionKey"], entity["RowKey"]] = (deepcopy(entity), f'W/"fixture-{self.version}"')

    def send(self, request, **kwargs):
        self.calls.append(request)
        url = unquote(request.url)
        if request.method == "GET":
            if "RowKey='" in url:
                key = (url.split("PartitionKey='")[1].split("'")[0], url.split("RowKey='")[1].split("'")[0])
                if key not in self.rows:
                    return Response(request, 404, {"odata.error": {"code": "ResourceNotFound", "message": {"value": "CANARY"}}})
                entity, etag = self.rows[key]
                return Response(request, 200, {**entity, "odata.etag": etag}, etag)
            partition = "alert" if "'alert'" in url else "observation"
            rows = [entity for (part, key), (entity, _) in sorted(self.rows.items()) if part == partition
                    and ("RowKey gt" not in url or key.startswith("audit:"))]
            if "RowKey gt" in url:
                lower = url.split("RowKey gt '")[1].split("'")[0]
                upper = url.split("RowKey lt '")[1].split("'")[0]
                rows = [row for row in rows if lower < row["RowKey"] < upper]
            return Response(request, 200, {"value": rows})
        if request.url.endswith("/$batch"):
            # These are the actual SDK subrequests, with their actual conditional headers.
            changeset = request.multipart_mixed_info[0][0]
            operations = changeset.multipart_mixed_info[0]
            update, audit = operations
            old = json.loads(update.body)
            event = json.loads(audit.body)
            existing = self.rows.get((old["PartitionKey"], old["RowKey"]))
            stale = existing is not None and update.headers.get("If-Match") != existing[1]
            if self.conflict or stale or self.fail_audit:
                self.conflict = False
                return Response(request, 202, parts=[Response(update, 412,
                    {"odata.error": {"code": "UpdateConditionNotSatisfied", "message": {"value": "CANARY"}}})])
            self._put(old); self._put(event)
            if self.lost:
                self.lost = False
                raise ServiceResponseError("CANARY-token-url")
            return Response(request, 202, parts=[Response(update, 204), Response(audit, 201)])
        if request.method == "DELETE":
            key = (url.split("PartitionKey='")[1].split("'")[0], url.split("RowKey='")[1].split("'")[0])
            self.rows.pop(key, None)
            return Response(request, 204)
        entity = json.loads(request.body)
        key = (entity["PartitionKey"], entity["RowKey"])
        if self.server_error and key[0] == "alert":
            return Response(request, 500, {"odata.error": {"code": "InternalError", "message": {"value": "CANARY"}}})
        if self.interleave and key[0] == "alert":
            callback, self.interleave = self.interleave, None
            callback()
        existing = self.rows.get(key)
        if request.method == "POST":
            if existing:
                return Response(request, 409, {"odata.error": {"code": "EntityAlreadyExists", "message": {"value": "CANARY"}}})
        elif (existing and request.headers.get("If-Match") != existing[1]
              and not (key[0] == "observation" and request.headers.get("If-Match") in (None, "*"))):
            return Response(request, 412, {"odata.error": {"code": "UpdateConditionNotSatisfied", "message": {"value": "CANARY"}}})
        self._put(entity)
        if self.lost_single and key[0] == "alert":
            self.lost_single = False
            raise ServiceResponseError("CANARY-unknown-ack")
        return Response(request, 204)


class TableAcknowledgementTests(unittest.TestCase):
    def setUp(self):
        self.wire = WireTransport()
        def actual_factory(**kwargs):
            self.assertEqual(kwargs["retry_total"], 0)
            self.client = TableClient(**kwargs, transport=self.wire)
            return self.client
        with patch("azure.data.tables.TableClient", side_effect=actual_factory):
            self.store = TableStateStore("https://fixtureaccount.table.core.windows.net",
                AzureNamedKeyCredential("fixtureaccount", "ZmFrZS1rZXk="), "CloudPcState",
                create_table=False)
        self.alerts = activate(self.store)
        self.fp = self.alerts[0].fingerprint

    def test_real_sdk_read_etag_transaction_and_history_filter(self):
        expected_etag = self.store._read_alert(self.fp)[1]
        event = acknowledge(self.store, self.fp)
        batch = next(call for call in self.wire.calls if call.url.endswith("/$batch"))
        update, audit = batch.multipart_mixed_info[0][0].multipart_mixed_info[0]
        self.assertEqual(update.method, "PUT")
        self.assertEqual(update.headers["If-Match"], expected_etag)
        self.assertNotEqual(update.headers["If-Match"], "*")
        self.assertEqual(audit.method, "POST")
        self.assertEqual(json.loads(update.body)["PartitionKey"], json.loads(audit.body)["PartitionKey"])
        self.assertEqual(self.store._read_event(self.fp, REQUEST), event)
        self.assertEqual(len(self.store.list_alerts()), 1)
        self.assertEqual(len(self.store.history(self.fp)["events"]), 1)
        self.assertFalse(any(call.method == "MERGE" for call in self.wire.calls))

    def test_real_sdk_412_recompute_preserves_concurrent_ack_during_timer(self):
        self.wire.interleave = lambda: acknowledge(self.store, self.fp)
        activate(self.store)
        self.assertTrue(self.store.get_alert(self.fp)["acknowledged"])
        self.assertEqual(self.store.get_alert(self.fp)["ackRevision"], 1)
        updates = [call for call in self.wire.calls if call.method == "PUT"]
        self.assertGreaterEqual(len(updates), 2)
        self.assertNotEqual(updates[0].headers["If-Match"], updates[-1].headers["If-Match"])
        self.store.mark_notified(self.fp, "2026-10-11T12:00:00Z")
        self.assertTrue(self.store.get_alert(self.fp)["acknowledged"])
        self.assertEqual(self.store.get_alert(self.fp)["notificationCount"], 1)

    def test_real_sdk_lost_response_replay_uses_event_once(self):
        self.wire.lost = True
        event = acknowledge(self.store, self.fp)
        self.assertEqual(event["kind"], "acknowledged")
        self.assertEqual(len([call for call in self.wire.calls if call.url.endswith("/$batch")]), 1)
        replay = acknowledge(self.store, self.fp, revision=0)
        self.assertEqual(event, replay)
        self.assertEqual(len([call for call in self.wire.calls if call.url.endswith("/$batch")]), 1)

    def test_real_sdk_atomic_audit_refusal_has_no_state_change_or_history(self):
        before = deepcopy(self.wire.rows)
        self.wire.fail_audit = True
        with self.assertRaisesRegex(StateError, "state_conflict"):
            acknowledge(self.store, self.fp)
        self.assertEqual(before, self.wire.rows)
        self.assertEqual(self.store.history(self.fp)["events"], [])

    def test_real_sdk_409_create_race_recomputes_without_upsert(self):
        self.wire.rows.clear()
        def competing_create():
            self.wire._put({"PartitionKey": "alert", "RowKey": self.fp,
                "payload": json.dumps(self.alerts[0].as_state())})
        self.wire.interleave = competing_create
        activate(self.store)
        value = self.store.get_alert(self.fp)
        self.assertEqual(value["notificationCount"], 0)
        self.assertIn("episode", value)
        self.assertTrue(any(call.method == "PUT" for call in self.wire.calls))

    def test_real_sdk_lost_notification_ack_no_second_increment_or_retry(self):
        self.wire.lost_single = True
        start = len(self.wire.calls)
        with self.assertRaisesRegex(StateError, "outcome_unknown"):
            self.store.mark_notified(self.fp, "2026-10-11T12:00:00Z")
        self.assertEqual(self.store.get_alert(self.fp)["notificationCount"], 1)
        self.assertEqual(len([call for call in self.wire.calls[start:] if call.method == "PUT"]), 1)

    def test_real_sdk_500_unknown_outcome_no_sdk_or_cas_retry(self):
        self.wire.server_error = True
        start = len(self.wire.calls)
        with self.assertRaisesRegex(StateError, "outcome_unknown"):
            self.store.mark_notified(self.fp, "2026-10-11T12:00:00Z")
        self.assertEqual(len([call for call in self.wire.calls[start:] if call.method == "PUT"]), 1)
        self.assertEqual(self.store.get_alert(self.fp)["notificationCount"], 0)

    def test_real_sdk_wildcard_missing_etag_and_foreign_payload_refused_before_write(self):
        for etag in (None, "", "*"):
            key = ("alert", self.fp)
            entity, _ = self.wire.rows[key]
            self.wire.rows[key] = (entity, etag)
            start = len(self.wire.calls)
            with self.assertRaises(StateError):
                self.store.mark_notified(self.fp, "2026-10-11T12:00:00Z")
            self.assertTrue(all(call.method == "GET" for call in self.wire.calls[start:]))
        entity, _ = self.wire.rows[key]
        payload = json.loads(entity["payload"])
        payload["fingerprint"] = "a" * 64
        entity["payload"] = json.dumps(payload)
        self.wire.rows[key] = (entity, 'W/"safe-fixture"')
        start = len(self.wire.calls)
        with self.assertRaises(StateError):
            self.store.mark_notified(self.fp, "2026-10-11T12:00:00Z")
        self.assertTrue(all(call.method == "GET" for call in self.wire.calls[start:]))

    def test_real_sdk_bounded_history_cursor_and_monitor_expiry_transaction(self):
        from datetime import timedelta
        acknowledge(self.store, self.fp)
        activate(self.store, NOW + timedelta(hours=2))
        first = self.store.history(self.fp, limit=1)
        second = self.store.history(self.fp, limit=1, cursor=first["cursor"])
        self.assertEqual(len(first["events"]), 1)
        self.assertEqual(len(second["events"]), 1)
        self.assertIsNone(second["cursor"])
        self.assertEqual({first["events"][0]["kind"], second["events"][0]["kind"]}, {"acknowledged", "expired"})
        queries = [unquote(call.url) for call in self.wire.calls if "RowKey%20gt" in call.url or "RowKey gt" in unquote(call.url)]
        self.assertEqual(len(queries), 2)
        self.assertTrue(all("$top=2" in query for query in queries))


if __name__ == "__main__":
    unittest.main()
