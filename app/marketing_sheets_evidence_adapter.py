from __future__ import annotations

import asyncio
import os
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from app.marketing_loop import MARKETING_REPOSITORY, MARKETING_WORKFLOW_TYPE, REVIEW_AGENT
from app.marketing_sheets_evidence_contract import (
    AttachGoogleSheetsReadOnlyEvidenceRequest,
    AttachGoogleSheetsReadOnlyEvidenceResponse,
)

HALL_DATA_AGENT = "hall-data-intelligence"
ANALYTICS_EVIDENCE_TYPE = "analytics_snapshot"
GOOGLE_SHEETS_SOURCE_MODE = "google_sheets_readonly"
DRIVE_CSV_SOURCE_MODE = "drive_csv_readonly"
GOOGLE_SHEETS_READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
GOOGLE_SHEETS_VALUES_BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets"
REQUIRED_SHEETS_COLUMNS = {
    "date_range_label",
    "source",
    "leads",
    "contacts_created",
    "deals_created",
    "sessions",
}


class MarketingSheetsEvidenceError(Exception):
    pass


class MarketingSheetsEvidenceValidationError(MarketingSheetsEvidenceError):
    pass


class MarketingSheetsSourceReadError(MarketingSheetsEvidenceError):
    pass


class MarketingSheetsEvidenceAgentBusClient(Protocol):
    async def list_work_items(self, *, repository: str | None = None) -> list[dict[str, Any]]: ...
    async def create_evidence_packet(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def attach_evidence_to_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class MarketingReadOnlyTabularSourceReader(Protocol):
    async def read_rows(self, payload: AttachGoogleSheetsReadOnlyEvidenceRequest) -> list[dict[str, Any]]: ...


class UnconfiguredMarketingSheetsReader:
    async def read_rows(self, payload: AttachGoogleSheetsReadOnlyEvidenceRequest) -> list[dict[str, Any]]:
        raise MarketingSheetsSourceReadError(
            "No Google Sheets or Drive CSV read-only source reader is configured for this environment."
        )


class ApprovedGoogleSheetsReadOnlySourceReader:
    def __init__(
        self,
        *,
        allowed_source_ids: tuple[str, ...] | list[str] | set[str],
        credentials_path: str | None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.allowed_source_ids = {source_id.strip() for source_id in allowed_source_ids if source_id.strip()}
        self.credentials_path = credentials_path
        self.timeout_seconds = timeout_seconds

    async def read_rows(self, payload: AttachGoogleSheetsReadOnlyEvidenceRequest) -> list[dict[str, Any]]:
        self._validate_request(payload)
        token = await asyncio.to_thread(self._access_token)
        values = await self._read_sheet_values(payload, token)
        return _rows_from_sheet_values(values, payload)

    def _validate_request(self, payload: AttachGoogleSheetsReadOnlyEvidenceRequest) -> None:
        if payload.source_type != "google_sheet":
            raise MarketingSheetsEvidenceValidationError("The approved read-only source reader only supports source_type=google_sheet.")
        if not payload.source_id.strip():
            raise MarketingSheetsEvidenceValidationError("source_id is required for Google Sheets read-only evidence.")
        if not self.allowed_source_ids:
            raise MarketingSheetsEvidenceValidationError("MARKETING_READONLY_ALLOWED_SOURCE_IDS must include the approved Google Sheet ID.")
        if payload.source_id not in self.allowed_source_ids:
            raise MarketingSheetsEvidenceValidationError("Requested Google Sheet source_id is not allowlisted for read-only evidence.")
        if not payload.sheet_name or not payload.sheet_name.strip():
            raise MarketingSheetsEvidenceValidationError("sheet_name is required for Google Sheets read-only evidence.")

    def _access_token(self) -> str:
        if not self.credentials_path:
            raise MarketingSheetsSourceReadError("GOOGLE_APPLICATION_CREDENTIALS is required for Google Sheets read-only evidence.")
        if not os.path.isfile(self.credentials_path):
            raise MarketingSheetsSourceReadError("GOOGLE_APPLICATION_CREDENTIALS must point to a readable service account file.")
        try:
            from google.auth.transport.requests import Request as GoogleAuthRequest
            from google.oauth2 import service_account
        except ImportError as exc:
            raise MarketingSheetsSourceReadError("google-auth[requests] is required for Google Sheets read-only evidence.") from exc
        try:
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=[GOOGLE_SHEETS_READONLY_SCOPE],
            )
            credentials.refresh(GoogleAuthRequest())
        except Exception as exc:
            raise MarketingSheetsSourceReadError("Unable to load or refresh Google Sheets read-only credentials.") from exc
        if not credentials.token:
            raise MarketingSheetsSourceReadError("Google Sheets read-only credentials did not return an access token.")
        return str(credentials.token)

    async def _read_sheet_values(self, payload: AttachGoogleSheetsReadOnlyEvidenceRequest, token: str) -> list[list[Any]]:
        range_name = quote(f"{payload.sheet_name}!A:Z", safe="")
        source_id = quote(payload.source_id, safe="")
        url = f"{GOOGLE_SHEETS_VALUES_BASE_URL}/{source_id}/values/{range_name}"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"majorDimension": "ROWS"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            raise MarketingSheetsSourceReadError("Google Sheets read failed for the approved read-only source.") from exc
        if response.status_code >= 400:
            raise MarketingSheetsSourceReadError("Google Sheets read failed for the approved read-only source.")
        try:
            body = response.json()
        except ValueError as exc:
            raise MarketingSheetsSourceReadError("Google Sheets read returned an invalid response body.") from exc
        values = body.get("values")
        if not isinstance(values, list):
            raise MarketingSheetsSourceReadError("Google Sheets read returned no tabular values.")
        return values


async def attach_google_sheets_readonly_evidence(
    *,
    agent_bus_client: MarketingSheetsEvidenceAgentBusClient,
    source_reader: MarketingReadOnlyTabularSourceReader,
    payload: AttachGoogleSheetsReadOnlyEvidenceRequest,
) -> AttachGoogleSheetsReadOnlyEvidenceResponse:
    work_item = await _find_work_item(agent_bus_client, payload.work_item_id)
    _validate_mapping(work_item, payload)
    rows = await _read_rows(source_reader, payload)
    metrics, source_breakdown = _normalize_rows(rows, payload)
    source_mode = _source_mode(payload.source_type)
    evidence_payload = {
        "work_item_id": payload.work_item_id,
        "repository": MARKETING_REPOSITORY,
        "implementation_agent": HALL_DATA_AGENT,
        "branch": "agent-integration",
        "commit_shas": [],
        "changed_files": [],
        "test_commands": ["marketing-google-sheets-readonly-attach"],
        "test_results": {
            "evidence_type": ANALYTICS_EVIDENCE_TYPE,
            "artifact_type": ANALYTICS_EVIDENCE_TYPE,
            "produced_by": HALL_DATA_AGENT,
            "workflow_id": payload.workflow_id,
            "workflow_type": MARKETING_WORKFLOW_TYPE,
            "source_mode": source_mode,
            "source_type": payload.source_type,
            "source_id": payload.source_id,
            "sheet_name": payload.sheet_name,
            "summary": "Read-only Google Sheets snapshot converted into analytics evidence."
            if payload.source_type == "google_sheet"
            else "Read-only Drive CSV snapshot converted into analytics evidence.",
            "date_range_label": payload.date_range_label,
            "metrics": metrics,
            "source_breakdown": source_breakdown,
            "findings": _findings(metrics),
            "confidence": "read_only_source",
            "mode": "mock_only",
            "live_platform_access": False,
            "write_access": False,
            "not_for_real_marketing_decisions": True,
            "approval_required": False,
            "mock_mode": False,
            "review_agent": REVIEW_AGENT,
        },
        "verification_summary": "Read-only tabular marketing source converted to analytics evidence. No writes occurred.",
        "assumptions": ["Source rows were read through a read-only adapter interface."],
        "unverified_items": ["This evidence is not approved for real marketing decisions."],
    }
    evidence = await agent_bus_client.create_evidence_packet(evidence_payload)
    evidence_packet_id = _response_id(evidence, "evidence_id")
    await agent_bus_client.attach_evidence_to_work_item(
        payload.work_item_id,
        {"evidence_id": evidence_packet_id, "actor": HALL_DATA_AGENT},
    )
    return AttachGoogleSheetsReadOnlyEvidenceResponse(
        workflow_id=payload.workflow_id,
        work_item_id=payload.work_item_id,
        evidence_packet_id=evidence_packet_id,
        source_mode=source_mode,
        source_type=payload.source_type,
        source_id=payload.source_id,
        metrics=metrics,
        source_breakdown=source_breakdown,
    )


async def _read_rows(
    source_reader: MarketingReadOnlyTabularSourceReader,
    payload: AttachGoogleSheetsReadOnlyEvidenceRequest,
) -> list[dict[str, Any]]:
    try:
        rows = await source_reader.read_rows(payload)
    except (MarketingSheetsEvidenceValidationError, MarketingSheetsSourceReadError):
        raise
    except Exception as exc:
        raise MarketingSheetsSourceReadError(f"Unable to read marketing source {payload.source_id}: {exc}") from exc
    if not rows:
        raise MarketingSheetsSourceReadError(f"No rows returned from marketing source {payload.source_id}.")
    return rows


async def _find_work_item(client: MarketingSheetsEvidenceAgentBusClient, work_item_id: str) -> dict[str, Any]:
    for item in await client.list_work_items(repository=MARKETING_REPOSITORY):
        if str(item.get("work_item_id") or item.get("id") or "") == work_item_id:
            return item
    raise MarketingSheetsEvidenceValidationError(f"Marketing work item not found: {work_item_id}")


def _validate_mapping(item: dict[str, Any], payload: AttachGoogleSheetsReadOnlyEvidenceRequest) -> None:
    metadata = _metadata(item)
    if payload.agent_id != HALL_DATA_AGENT or item.get("owner_agent") != HALL_DATA_AGENT:
        raise MarketingSheetsEvidenceValidationError("Google Sheets read-only evidence is only supported for hall-data-intelligence.")
    if metadata.get("workflow_id") != payload.workflow_id:
        raise MarketingSheetsEvidenceValidationError("Requested workflow_id does not match the work item workflow_id.")
    if metadata.get("workflow_type") != MARKETING_WORKFLOW_TYPE:
        raise MarketingSheetsEvidenceValidationError("Unsupported marketing workflow type for Google Sheets read-only evidence.")
    if metadata.get("work_item_role") not in {"specialist", "specialist_evidence"}:
        raise MarketingSheetsEvidenceValidationError("Google Sheets read-only evidence can only attach to specialist work items.")
    if metadata.get("live_platform_access") is not False:
        raise MarketingSheetsEvidenceValidationError("Google Sheets read-only evidence requires live_platform_access=false on the work item.")


def _normalize_rows(
    rows: list[dict[str, Any]],
    payload: AttachGoogleSheetsReadOnlyEvidenceRequest,
) -> tuple[dict[str, float | int], list[dict[str, float | int | str]]]:
    mapping = payload.mapping
    totals = {
        "leads": 0,
        "contacts_created": 0,
        "deals_created": 0,
        "sessions": 0,
    }
    source_breakdown: dict[str, dict[str, float | int | str]] = {}
    for row in rows:
        source = str(row.get(mapping.source) or "unknown")
        leads = _int_value(row, mapping.leads)
        contacts_created = _int_value(row, mapping.contacts_created)
        deals_created = _int_value(row, mapping.deals_created)
        sessions = _int_value(row, mapping.sessions)
        totals["leads"] += leads
        totals["contacts_created"] += contacts_created
        totals["deals_created"] += deals_created
        totals["sessions"] += sessions
        bucket = source_breakdown.setdefault(
            source,
            {"source": source, "leads": 0, "contacts_created": 0, "deals_created": 0, "sessions": 0},
        )
        bucket["leads"] = int(bucket["leads"]) + leads
        bucket["contacts_created"] = int(bucket["contacts_created"]) + contacts_created
        bucket["deals_created"] = int(bucket["deals_created"]) + deals_created
        bucket["sessions"] = int(bucket["sessions"]) + sessions
    metrics: dict[str, float | int] = {
        **totals,
        "deal_created_rate_from_leads": _rate(float(totals["deals_created"]), float(totals["leads"])),
    }
    return metrics, sorted(source_breakdown.values(), key=lambda item: str(item["source"]))


def _rows_from_sheet_values(values: list[list[Any]], payload: AttachGoogleSheetsReadOnlyEvidenceRequest) -> list[dict[str, Any]]:
    if len(values) < 2:
        raise MarketingSheetsSourceReadError("Google Sheets source must include a header row and at least one data row.")
    headers = [str(value).strip() for value in values[0]]
    required_columns = _required_columns(payload)
    missing = sorted(column for column in required_columns if column not in headers)
    if missing:
        raise MarketingSheetsSourceReadError(f"Google Sheets source is missing expected columns: {', '.join(missing)}.")
    rows: list[dict[str, Any]] = []
    for value_row in values[1:]:
        row = {header: value_row[index] if index < len(value_row) else "" for index, header in enumerate(headers)}
        if str(row.get("date_range_label") or "").strip() == payload.date_range_label:
            rows.append(row)
    if not rows:
        raise MarketingSheetsSourceReadError(f"No rows matched date_range_label={payload.date_range_label}.")
    return rows


def _required_columns(payload: AttachGoogleSheetsReadOnlyEvidenceRequest) -> set[str]:
    mapping = payload.mapping
    return {
        "date_range_label",
        mapping.source,
        mapping.leads,
        mapping.contacts_created,
        mapping.deals_created,
        mapping.sessions,
    }


def _int_value(row: dict[str, Any], key: str) -> int:
    value = row.get(key, 0)
    if value in {None, ""}:
        return 0
    try:
        parsed = int(float(str(value).replace(",", "")))
    except ValueError as exc:
        raise MarketingSheetsEvidenceValidationError(f"Invalid numeric value for {key}: {value}") from exc
    if parsed < 0:
        raise MarketingSheetsEvidenceValidationError(f"Negative values are not supported for {key}.")
    return parsed


def _findings(metrics: dict[str, float | int]) -> list[str]:
    return [
        f"Read-only source reported {metrics['leads']} leads and {metrics['deals_created']} deals created.",
        f"Deal-created rate from leads is {metrics['deal_created_rate_from_leads']}.",
    ]


def _source_mode(source_type: str) -> str:
    return DRIVE_CSV_SOURCE_MODE if source_type == "drive_csv" else GOOGLE_SHEETS_SOURCE_MODE


def _rate(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _response_id(response: dict[str, Any], key: str) -> str:
    value = response.get(key) or response.get("id")
    if not value:
        raise MarketingSheetsEvidenceValidationError(f"Agent Bus response did not include {key}.")
    return str(value)
