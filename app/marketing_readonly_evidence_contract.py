from __future__ import annotations

from pydantic import BaseModel, Field


class WeeklyMarketingSnapshotFixture(BaseModel):
    business_unit: str = Field(min_length=1)
    date_range_label: str = Field(min_length=1)
    website_sessions: int = Field(ge=0)
    leads: int = Field(ge=0)
    qualified_leads: int = Field(default=0, ge=0)
    deals_created: int = Field(ge=0)
    pipeline_value: float = Field(default=0, ge=0)
    closed_won_value: float = Field(default=0, ge=0)
    notes: str | None = None


class AttachReadOnlyFixtureEvidenceRequest(BaseModel):
    work_item_id: str = Field(min_length=1)
    workflow_id: str | None = None
    fixture: WeeklyMarketingSnapshotFixture


class AttachReadOnlyFixtureEvidenceResponse(BaseModel):
    workflow_id: str | None = None
    work_item_id: str
    agent_id: str = "hall-data-intelligence"
    evidence_type: str = "analytics_snapshot"
    evidence_packet_id: str
    source_mode: str = "read_only_fixture"
    live_platform_access: bool = False
    write_access: bool = False
    not_for_real_marketing_decisions: bool = True
    derived_metrics: dict[str, float]
