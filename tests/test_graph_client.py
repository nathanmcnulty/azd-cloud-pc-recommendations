from __future__ import annotations

import sys
from pathlib import Path
import unittest


APP_ROOT = Path(__file__).resolve().parents[1] / "src" / "cloud-pc-monitor"
sys.path.insert(0, str(APP_ROOT))

from cloudpc_monitor.graph_client import (  # noqa: E402
    GraphClient,
    parse_report_payload,
)


class FakeCredential:
    def get_token(self, scope: str):
        self.scope = scope
        return type("Token", (), {"token": "fixture-token"})()


class FakeResponse:
    def __init__(self, status_code: int, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = ""
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


class GraphClientTests(unittest.TestCase):
    def test_report_stream_schema_is_converted_to_rows(self) -> None:
        rows = parse_report_payload(
            {
                "Schema": [{"Column": "CloudPcId"}, {"Column": "UsageInsight"}],
                "Values": [["pc-1", "Underutilized"]],
            }
        )
        self.assertEqual(rows, [{"CloudPcId": "pc-1", "UsageInsight": "Underutilized"}])

    def test_recommendation_report_collects_later_pages(self) -> None:
        session = FakeSession([
            FakeResponse(200, {"Schema": [{"Column": "CloudPcId"}], "Values": [["pc-1"], ["pc-2"]]}),
            FakeResponse(200, {"Schema": [{"Column": "CloudPcId"}], "Values": [["pc-3"]]}),
        ])
        client = GraphClient(credential=FakeCredential(), session=session)

        self.assertEqual(client.get_recommendations(page_size=2), [
            {"CloudPcId": "pc-1"}, {"CloudPcId": "pc-2"}, {"CloudPcId": "pc-3"},
        ])
        self.assertEqual([call[2]["json"]["skip"] for call in session.calls], [0, 2])
        self.assertTrue(all(call[1].startswith("https://graph.microsoft.com/v1.0/") for call in session.calls))

    def test_recommendation_report_rejects_repeated_pages(self) -> None:
        page = {"Schema": [{"Column": "CloudPcId"}], "Values": [["pc-1"]]}
        client = GraphClient(credential=FakeCredential(), session=FakeSession([
            FakeResponse(200, page), FakeResponse(200, page),
        ]))
        with self.assertRaisesRegex(Exception, "repeated a page"):
            client.get_recommendations(page_size=1)

    def test_recommendation_report_rejects_a_malformed_later_page(self) -> None:
        client = GraphClient(credential=FakeCredential(), session=FakeSession([
            FakeResponse(200, {"value": [{"CloudPcId": "pc-1"}]}),
            FakeResponse(200, {"value": "not an array"}),
        ]))
        with self.assertRaisesRegex(Exception, "not an array"):
            client.get_recommendations(page_size=1)

    def test_collection_paginates_and_retries_throttling(self) -> None:
        session = FakeSession(
            [
                FakeResponse(429, {"error": "throttled"}, {"Retry-After": "0"}),
                FakeResponse(
                    200,
                    {
                        "value": [{"id": "one"}],
                        "@odata.nextLink": "https://graph.test/v1.0/next",
                    },
                ),
                FakeResponse(200, {"value": [{"id": "two"}]}),
            ]
        )
        delays = []
        client = GraphClient(
            api_version="v1.0",
            credential=FakeCredential(),
            session=session,
            sleeper=delays.append,
        )

        values = client.get_collection("/items")

        self.assertEqual(values, [{"id": "one"}, {"id": "two"}])
        self.assertEqual(len(session.calls), 3)
        self.assertEqual(delays, [0.0])
        self.assertNotIn("fixture-token", session.calls[0][2]["headers"]["Accept"])


if __name__ == "__main__":
    unittest.main()
