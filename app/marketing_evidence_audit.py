from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from app.config import Settings
from app.marketing_evidence_audit_contract import MarketingEvidenceAuditEvent
from app.marketing_sheets_evidence_adapter import GOOGLE_SHEETS_SOURCE_MODE
from app.marketing_sheets_evidence_contract import AttachGoogleSheetsReadOnlyEvidenceRequest


class MarketingEvidenceAuditRepository(Protocol):
    async def record_event(self, event: MarketingEvidenceAuditEvent) -> MarketingEvidenceAuditEvent: ...

    async def list_events(
        self,
        *,
        workflow_id: str | None = None,
        source_mode: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[MarketingEvidenceAuditEvent]: ...


class InMemoryMarketingEvidenceAuditRepository:
    def __init__(self) -> None:
        self.events: list[MarketingEvidenceAuditEvent] = []

    async def record_event(self, event: MarketingEvidenceAuditEvent) -> MarketingEvidenceAuditEvent:
        self.events.append(event)
        return event

    async def list_events(
        self,
        *,
        workflow_id: str | None = None,
        source_mode: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[MarketingEvidenceAuditEvent]:
        return _filter_events(self.events, workflow_id=workflow_id, source_mode=source_mode, status=status, limit=limit)


class JsonlMarketingEvidenceAuditRepository:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    async def record_event(self, event: MarketingEvidenceAuditEvent) -> MarketingEvidenceAuditEvent:
        await asyncio.to_thread(self._append_event, event)
        return event

    async def list_events(
        self,
        *,
        workflow_id: str | None = None,
        source_mode: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[MarketingEvidenceAuditEvent]:
        events = await asyncio.to_thread(self._read_events)
        return _filter_events(events, workflow_id=workflow_id, source_mode=source_mode, status=status, limit=limit)

    def _append_event(self, event: MarketingEvidenceAuditEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")

    def _read_events(self) -> list[MarketingEvidenceAuditEvent]:
        if not self.path.exists():
            return []
        events: list[MarketingEvidenceAuditEvent] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                events.append(MarketingEvidenceAuditEvent.model_validate(json.loads(line)))
        return events


def build_marketing_evidence_audit_event(
    *,
    payload: AttachGoogleSheetsReadOnlyEvidenceRequest,
    settings: Settings,
    status: str,
    failure_reason: str | None = None,
    evidence_packet_id: str | None = None,
) -> MarketingEvidenceAuditEvent:
    source_id = payload.source_id or ""
    sanitized_failure_reason = _sanitize_failure_reason(failure_reason, source_id)
    return MarketingEvidenceAuditEvent(
        audit_event_id=f"meaud-{uuid4()}",
        workflow_id=payload.workflow_id,
        work_item_id=payload.work_item_id,
        agent_id=payload.agent_id,
        source_type=payload.source_type,
        source_mode=_source_mode_for_payload(payload),
        source_id_hash=_hash_source_id(source_id),
        source_id_last_6=_last_6(source_id),
        sheet_name=payload.sheet_name,
        date_range_label=payload.date_range_label,
        allowlist_passed=bool(source_id and source_id in settings.marketing_readonly_allowed_source_ids),
        credentials_present=bool(settings.google_application_credentials),
        write_access=False,
        live_platform_access=False,
        status=status,  # type: ignore[arg-type]
        failure_reason=sanitized_failure_reason,
        evidence_packet_id=evidence_packet_id,
        created_at=datetime.now(UTC).isoformat(),
    )


def audit_path_from_settings(settings: Settings) -> str | None:
    if not settings.orchestrator_db_path:
        return None
    path = Path(settings.orchestrator_db_path)
    if path.suffix:
        return str(path.with_suffix(path.suffix + ".marketing_evidence_audit.jsonl"))
    return str(path / "marketing_evidence_audit.jsonl")


def _filter_events(
    events: list[MarketingEvidenceAuditEvent],
    *,
    workflow_id: str | None,
    source_mode: str | None,
    status: str | None,
    limit: int,
) -> list[MarketingEvidenceAuditEvent]:
    filtered = [
        event
        for event in events
        if (workflow_id is None or event.workflow_id == workflow_id)
        and (source_mode is None or event.source_mode == source_mode)
        and (status is None or event.status == status)
    ]
    return list(reversed(filtered))[: max(1, min(limit, 500))]


def _source_mode_for_payload(payload: AttachGoogleSheetsReadOnlyEvidenceRequest) -> str:
    return GOOGLE_SHEETS_SOURCE_MODE if payload.source_type == "google_sheet" else "drive_csv_readonly"


def _hash_source_id(source_id: str) -> str:
    if not source_id:
        return ""
    return hashlib.sha256(source_id.encode("utf-8")).hexdigest()


def _last_6(source_id: str) -> str:
    return source_id[-6:] if source_id else ""


def _sanitize_failure_reason(failure_reason: str | None, source_id: str) -> str | None:
    if failure_reason is None:
        return None
    sanitized = failure_reason
    if source_id:
        sanitized = sanitized.replace(source_id, "[redacted_source_id]")
    return sanitized
