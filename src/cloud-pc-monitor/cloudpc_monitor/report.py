"""Audit report exporters."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any


class NullReportExporter:
    """No-op exporter used by the local fixture command."""

    def write(self, report: dict[str, Any]) -> str:
        return ""


class BlobReportExporter:
    """Write reports to a dedicated Blob Storage container using managed identity."""

    def __init__(
        self,
        *,
        account_url: str,
        credential: Any,
        container_name: str,
    ) -> None:
        self.account_url = account_url.rstrip("/")
        self.credential = credential
        self.container_name = container_name

    def write(self, report: dict[str, Any]) -> str:
        from azure.storage.blob import BlobServiceClient

        service = BlobServiceClient(
            account_url=self.account_url,
            credential=self.credential,
        )
        container = service.get_container_client(self.container_name)
        try:
            container.create_container()
        except Exception as exc:
            # The Bicep deployment creates the container. A repeated timer run
            # must treat an existing container as the normal idempotent path.
            if getattr(exc, "error_code", None) not in {
                "ContainerAlreadyExists",
                "ContainerAlreadyOwnedByYou",
            }:
                raise
        observed_at = _parse_datetime(report["observedAt"])
        blob_name = (
            f"{observed_at:%Y/%m/%d}/{report['runId']}.json"
        )
        blob = container.get_blob_client(blob_name)
        blob.upload_blob(
            json.dumps(report, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
            overwrite=True,
            content_type="application/json",
        )
        return f"{self.account_url}/{self.container_name}/{blob_name}"


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
