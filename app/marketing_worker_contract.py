from __future__ import annotations

from pydantic import BaseModel, Field


class MarketingWorkerRunOnceRequest(BaseModel):
    workflow_id: str | None = None
    max_items: int = Field(default=4, ge=1, le=25)


class MarketingWorkerResult(BaseModel):
    worker_run_id: str
    workflow_id: str | None = None
    agent_id: str
    work_item_id: str
    status: str
    evidence_packet_id: str | None = None
    mock_mode: bool = True
    live_platform_access: bool = False
    next_action: str = "ready_for_review"
    skipped_reason: str | None = None


class MarketingWorkerRunOnceResponse(BaseModel):
    worker_run_id: str
    workflow_id: str | None = None
    processed: int = 0
    results: list[MarketingWorkerResult] = Field(default_factory=list)
