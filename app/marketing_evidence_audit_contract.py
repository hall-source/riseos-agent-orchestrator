from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AuditStatus = Literal["success", "failed"]


class MarketingEvidenceAuditEvent(BaseModel):
    audit_event_id: str
    event_type: str = "marketing_readonly_evidence_attach_attempt"
    workflow_id: str
    work_item_id: str
    agent_id: str
    source_type: str
    source_mode: str
    source_id_hash: str
    source_id_last_6: str
    sheet_name: str | None = None
    date_range_label: str
    requested_by: str = "admin_token_authenticated_request"
    allowlist_passed: bool
    credentials_present: bool
    write_access: bool = False
    live_platform_access: bool = False
    status: AuditStatus
    failure_reason: str | None = None
    evidence_packet_id: str | None = None
    created_at: str


class MarketingEvidenceAuditListResponse(BaseModel):
    events: list[MarketingEvidenceAuditEvent] = Field(default_factory=list)
