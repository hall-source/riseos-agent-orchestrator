from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SourceType = Literal["google_sheet"]


class WeeklyMarketingSnapshotReadOnlyRunRequest(BaseModel):
    business_unit: str = "RISE Commercial District"
    requested_by: str = "Hall"
    date_range_label: str = "last_7_days"
    source_type: SourceType = "google_sheet"
    source_id: str = Field(min_length=1)
    sheet_name: str = Field(default="Weekly Marketing Snapshot", min_length=1)
    run_mock_workers: bool = True
    run_mock_governance: bool = True


class WeeklyMarketingSnapshotReadOnlyRunResponse(BaseModel):
    workflow_id: str
    created_work_items: list[str] = Field(default_factory=list)
    data_work_item_id: str
    analytics_evidence_packet_id: str
    worker_run_id: str | None = None
    governance_run_id: str | None = None
    review_artifact_id: str | None = None
    synthesis_artifact_id: str | None = None
    audit_events_url: str
    summary_url: str
    approval_required: bool = True
    human_approval_performed: bool = False
    live_platform_access: bool = False
    write_access: bool = False
    not_for_real_marketing_decisions: bool = True
    next_action: str = (
        "Hall must review the synthesis and call the approval endpoint manually. "
        "No production action has been authorized."
    )
