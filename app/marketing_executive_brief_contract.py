from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class MarketingExecutiveSummarySection(BaseModel):
    headline: str
    summary: str


class MarketingExecutiveReviewSection(BaseModel):
    ready: bool = False
    artifact_id: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    approval_recommendation: str | None = None


class MarketingExecutiveSynthesisSection(BaseModel):
    ready: bool = False
    artifact_id: str | None = None
    summary: str | None = None


class MarketingExecutiveBriefLinks(BaseModel):
    summary_url: str
    audit_events_url: str
    approval_url: str


class MarketingExecutiveBriefResponse(BaseModel):
    workflow_id: str
    brief_type: Literal["weekly_marketing_executive_brief"] = "weekly_marketing_executive_brief"
    business_unit: str
    date_range_label: str | None = None
    status: str
    approval_state: str
    approval_required: bool = True
    human_approval_complete: bool = False
    live_platform_access: bool = False
    write_access: bool = False
    not_for_real_marketing_decisions: bool = True
    executive_summary: MarketingExecutiveSummarySection
    scorecard: dict[str, int | float] = Field(default_factory=dict)
    channel_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    review: MarketingExecutiveReviewSection
    synthesis: MarketingExecutiveSynthesisSection
    recommended_next_action: str
    links: MarketingExecutiveBriefLinks
