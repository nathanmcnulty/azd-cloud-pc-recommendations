"""Small Microsoft Graph client with pagination and throttling handling."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import time
from typing import Any, Callable, Mapping

try:
    import requests
except ImportError:  # pragma: no cover - the deployed app declares requests
    requests = None  # type: ignore[assignment]

from .config import Settings


class GraphApiError(RuntimeError):
    """A Microsoft Graph request failed after retry handling."""

    def __init__(self, method: str, url: str, status_code: int, detail: str):
        self.method = method
        self.url = url
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Graph {method} {url} returned HTTP {status_code}: {detail}")


@dataclass
class GraphSnapshot:
    """Data collected for one monitor run."""

    cloud_pcs: list[dict[str, Any]] = field(default_factory=list)
    managed_devices: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class GraphClient:
    """Microsoft Graph REST client using an Entra credential."""

    _RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        *,
        api_version: str = "beta",
        credential: Any | None = None,
        session: Any | None = None,
        max_retries: int = 4,
        timeout_seconds: int = 30,
        sleeper: Callable[[float], None] = time.sleep,
        base_url: str = "https://graph.microsoft.com",
    ) -> None:
        self.api_version = api_version
        self.credential = credential or self._new_default_credential()
        self.session = session or _new_requests_session()
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.sleeper = sleeper
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def _new_default_credential() -> Any:
        from azure.identity import DefaultAzureCredential

        return DefaultAzureCredential()

    def collect(self, settings: Settings) -> GraphSnapshot:
        """Collect Cloud PC, managed-device, and optional report data."""

        snapshot = GraphSnapshot()
        snapshot.cloud_pcs = self.get_cloud_pcs(
            page_size=settings.graph_page_size,
            api_version=settings.graph_api_version,
        )

        try:
            snapshot.managed_devices = self.get_managed_devices(
                page_size=settings.graph_page_size
            )
        except GraphApiError as exc:
            snapshot.warnings.append(
                "Managed-device collection failed; stale and compliance signals "
                f"were not complete ({exc.status_code})."
            )
            logging.warning("Managed-device collection failed: %s", exc)

        if settings.recommendations_enabled:
            try:
                snapshot.recommendations = self.get_recommendations(
                    page_size=settings.graph_page_size
                )
            except GraphApiError as exc:
                snapshot.warnings.append(
                    "Recommendation report collection failed; recommendation "
                    f"signals were not complete ({exc.status_code})."
                )
                logging.warning("Recommendation collection failed: %s", exc)

        return snapshot

    def get_cloud_pcs(
        self, *, page_size: int = 100, api_version: str | None = None
    ) -> list[dict[str, Any]]:
        if (api_version or self.api_version) == "v1.0":
            select = (
                "id,displayName,userPrincipalName,managedDeviceId,"
                "managedDeviceName,lastModifiedDateTime,provisionedDateTime,"
                "servicePlanId,servicePlanName,provisioningPolicyName,"
                "gracePeriodEndDateTime"
            )
        else:
            select = (
                "id,displayName,userPrincipalName,status,statusDetail,"
                "managedDeviceId,managedDeviceName,lastLoginResult,"
                "lastLogoffDateTime,lastModifiedDateTime,provisionedDateTime,"
                "servicePlanId,servicePlanName,provisioningPolicyName,"
                "gracePeriodEndDateTime,connectivityResult"
            )
        return self.get_collection(
            "/deviceManagement/virtualEndpoint/cloudPCs",
            api_version=api_version,
            params={"$select": select, "$top": str(page_size)},
            headers={"Prefer": "include-unknown-enum-members"},
        )

    def get_managed_devices(self, *, page_size: int = 100) -> list[dict[str, Any]]:
        return self.get_collection(
            "/deviceManagement/managedDevices",
            api_version="v1.0",
            params={
                "$select": (
                    "id,deviceName,lastSyncDateTime,complianceState,"
                    "managementState,azureADDeviceId,userPrincipalName"
                ),
                "$top": str(page_size),
            },
        )

    def get_recommendations(self, *, page_size: int = 100) -> list[dict[str, Any]]:
        response = self.post_json(
            "/deviceManagement/virtualEndpoint/report/"
            "retrieveCloudPcRecommendationReports",
            api_version="v1.0",
            body={
                "reportType": "cloudPcUsageCategoryReport",
                "filter": "",
                "select": [
                    "CloudPcId",
                    "ManagedDeviceName",
                    "UserPrincipalName",
                    "ServicePlanId",
                    "ServicePlanName",
                    "UsageInsight",
                    "RecommendedPlanId",
                    "RecommendedPlanName",
                ],
                "search": "",
                "skip": 0,
                "top": page_size,
            },
        )
        return parse_report_payload(response)

    def get_collection(
        self,
        path: str,
        *,
        api_version: str | None = None,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        url = self._url(path, api_version)
        items: list[dict[str, Any]] = []
        first_request = True
        while url:
            response = self._request(
                "GET",
                url,
                params=params if first_request else None,
                headers=headers,
            )
            first_request = False
            payload = response.json()
            values = payload.get("value", []) if isinstance(payload, dict) else []
            if not isinstance(values, list):
                raise GraphApiError("GET", url, response.status_code, "value was not an array")
            items.extend(item for item in values if isinstance(item, dict))
            next_link = payload.get("@odata.nextLink") if isinstance(payload, dict) else None
            url = next_link if isinstance(next_link, str) and next_link else ""
        return items

    def post_json(
        self,
        path: str,
        *,
        api_version: str | None = None,
        body: Mapping[str, Any],
    ) -> Any:
        response = self._request(
            "POST",
            self._url(path, api_version),
            json=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            return response.json()
        except ValueError as exc:
            raise GraphApiError(
                "POST", self._url(path, api_version), response.status_code, "response was not JSON"
            ) from exc

    def _url(self, path: str, api_version: str | None) -> str:
        version = api_version or self.api_version
        normalized_path = path if path.startswith("/") else f"/{path}"
        return f"{self.base_url}/{version}{normalized_path}"

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        supplied_headers = dict(kwargs.pop("headers", {}) or {})
        supplied_headers.setdefault("Accept", "application/json")
        for attempt in range(self.max_retries + 1):
            token = self.credential.get_token(
                "https://graph.microsoft.com/.default"
            ).token
            headers = dict(supplied_headers)
            headers["Authorization"] = f"Bearer {token}"
            response = self.session.request(
                method,
                url,
                headers=headers,
                timeout=self.timeout_seconds,
                **kwargs,
            )
            if response.status_code not in self._RETRYABLE_STATUS_CODES:
                if not response.ok:
                    detail = (response.text or "").replace("\n", " ")[:500]
                    raise GraphApiError(method, url, response.status_code, detail)
                return response

            if attempt >= self.max_retries:
                detail = (response.text or "").replace("\n", " ")[:500]
                raise GraphApiError(method, url, response.status_code, detail)

            retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
            delay = retry_after if retry_after is not None else min(60.0, 2**attempt)
            logging.warning(
                "Graph request %s %s returned %s; retrying in %.1fs.",
                method,
                url,
                response.status_code,
                delay,
            )
            self.sleeper(delay)

        raise AssertionError("unreachable")


def parse_report_payload(payload: Any) -> list[dict[str, Any]]:
    """Convert the Graph report stream-shaped JSON into ordinary rows."""

    if isinstance(payload, dict) and isinstance(payload.get("value"), list):
        return [item for item in payload["value"] if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    schema = payload.get("Schema") or payload.get("schema") or []
    values = payload.get("Values") or payload.get("values") or []
    columns = []
    for item in schema:
        if isinstance(item, dict):
            column = item.get("Column") or item.get("column")
            if column:
                columns.append(str(column))
    rows: list[dict[str, Any]] = []
    for value_row in values:
        if isinstance(value_row, list):
            rows.append(
                {
                    column: value_row[index] if index < len(value_row) else None
                    for index, column in enumerate(columns)
                }
            )
    return rows


def _retry_after_seconds(raw: Any) -> float | None:
    try:
        value = float(str(raw))
    except (TypeError, ValueError):
        return None
    return max(0.0, min(value, 300.0))


def _new_requests_session() -> Any:
    if requests is None:
        raise RuntimeError(
            "The requests package is required for live Graph collection. "
            "Install src/cloud-pc-monitor/requirements.txt."
        )
    return requests.Session()
