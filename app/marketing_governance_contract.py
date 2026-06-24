from __future__ import annotations

from pydantic import BaseModel


class MarketingGovernanceRunOnceRequest(BaseModel):
    workflow_id: str
    run_reviewer: bool = True
    run_hq_synthesis: bool = True


class MarketingGovernanceStageResult(BaseModel):
    status: str
    work_item_id: str | None = None
    artifact_id: str | None = None
    artifact_type: str | None = None
    skipped_reason: str | None = None


class MarketingGovernanceRunOnceResponse(BaseModel):
    governance_run_id: str
    workflow_id: str
    reviewer_result: MarketingGovernanceStageResult | None = None
    hq_result: MarketingGovernanceStageResult | None = None
    mock_mode: bool = True
    live_platform_access: bool = False
    next_action: str
