from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MarketingApprovalDecision = Literal["approve_mock", "reject_mock", "request_changes"]


class MarketingApprovalRequest(BaseModel):
    decision: MarketingApprovalDecision
    approved_by: str = Field(min_length=1)
    notes: str | None = None
    artifact_id: str | None = None


class MarketingApprovalRecord(BaseModel):
    workflow_id: str
    approval_state: str = "not_approved"
    approval_artifact_id: str | None = None
    approved_by: str | None = None
    decision: MarketingApprovalDecision | None = None
    notes: str | None = None
    approved_artifact_id: str | None = None
    approved_artifact_type: str | None = None
    mock_mode: bool = True
    confidence: str = "mock_only"
    live_platform_access: bool = False
    no_production_write_performed: bool = True
    no_external_platform_action_performed: bool = True
    not_for_real_marketing_decisions: bool = True
    created_at: str | None = None
    next_action: str | None = None
