from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SourceType = Literal["google_sheet", "drive_csv"]


class MarketingSheetsFieldMapping(BaseModel):
    leads: str = "leads"
    contacts_created: str = "contacts_created"
    deals_created: str = "deals_created"
    sessions: str = "sessions"
    source: str = "source"


class AttachGoogleSheetsReadOnlyEvidenceRequest(BaseModel):
    workflow_id: str = Field(min_length=1)
    agent_id: str = "hall-data-intelligence"
    work_item_id: str = Field(min_length=1)
    source_type: SourceType = "google_sheet"
    source_id: str = Field(min_length=1)
    sheet_name: str | None = None
    date_range_label: str = Field(min_length=1)
    mapping: MarketingSheetsFieldMapping = Field(default_factory=MarketingSheetsFieldMapping)


class AttachGoogleSheetsReadOnlyEvidenceResponse(BaseModel):
    workflow_id: str
    work_item_id: str
    agent_id: str = "hall-data-intelligence"
    evidence_type: str = "analytics_snapshot"
    evidence_packet_id: str
    source_mode: str
    source_type: SourceType
    source_id: str
    live_platform_access: bool = False
    write_access: bool = False
    not_for_real_marketing_decisions: bool = True
    metrics: dict[str, float | int]
    source_breakdown: list[dict[str, float | int | str]] = Field(default_factory=list)
