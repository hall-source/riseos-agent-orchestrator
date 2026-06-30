from __future__ import annotations

from typing import Any, Protocol

from app.config import Settings
from app.marketing_evidence_audit import MarketingEvidenceAuditRepository, build_marketing_evidence_audit_event
from app.marketing_governance import run_marketing_governance_once
from app.marketing_loop import (
    MARKETING_REPOSITORY,
    MockWeeklyMarketingBriefRequest,
    create_mock_weekly_marketing_command_brief,
)
from app.marketing_sheets_evidence_adapter import (
    HALL_DATA_AGENT,
    MarketingReadOnlyTabularSourceReader,
    attach_google_sheets_readonly_evidence,
)
from app.marketing_sheets_evidence_contract import AttachGoogleSheetsReadOnlyEvidenceRequest
from app.marketing_worker import run_marketing_worker_once
from app.weekly_marketing_snapshot_readonly_contract import (
    WeeklyMarketingSnapshotReadOnlyRunRequest,
    WeeklyMarketingSnapshotReadOnlyRunResponse,
)


class WeeklyMarketingSnapshotReadOnlyError(Exception):
    pass


class WeeklyMarketingSnapshotReadOnlyValidationError(WeeklyMarketingSnapshotReadOnlyError):
    pass


class WeeklyMarketingSnapshotAgentBusClient(Protocol):
    async def list_work_items(self, *, repository: str | None = None) -> list[dict[str, Any]]: ...
    async def register_agent(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def heartbeat_agent(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def create_work_item(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def create_evidence_packet(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def attach_evidence_to_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def claim_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def transition_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def complete_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def get_evidence_packet(self, evidence_id: str) -> dict[str, Any]: ...


async def run_weekly_marketing_snapshot_readonly_workflow(
    *,
    payload: WeeklyMarketingSnapshotReadOnlyRunRequest,
    settings: Settings,
    agent_bus_client: WeeklyMarketingSnapshotAgentBusClient,
    source_reader: MarketingReadOnlyTabularSourceReader,
    audit_repository: MarketingEvidenceAuditRepository,
    mission_control_url: str,
) -> WeeklyMarketingSnapshotReadOnlyRunResponse:
    _preflight_optional_flags(payload, settings)
    workflow = await create_mock_weekly_marketing_command_brief(
        MockWeeklyMarketingBriefRequest(
            business_unit=payload.business_unit,
            requested_by=payload.requested_by,
            date_range_label=payload.date_range_label,
            auto_complete_specialists=False,
        ),
        agent_bus_client=agent_bus_client,
        mission_control_url=mission_control_url,
    )
    data_work_item_id = await _find_data_work_item_id(agent_bus_client, workflow.workflow_id)
    evidence_payload = AttachGoogleSheetsReadOnlyEvidenceRequest(
        workflow_id=workflow.workflow_id,
        agent_id=HALL_DATA_AGENT,
        work_item_id=data_work_item_id,
        source_type=payload.source_type,
        source_id=payload.source_id,
        sheet_name=payload.sheet_name,
        date_range_label=payload.date_range_label,
    )
    try:
        evidence = await attach_google_sheets_readonly_evidence(
            agent_bus_client=agent_bus_client,
            source_reader=source_reader,
            payload=evidence_payload,
        )
        await audit_repository.record_event(
            build_marketing_evidence_audit_event(
                payload=evidence_payload,
                settings=settings,
                status="success",
                evidence_packet_id=evidence.evidence_packet_id,
            )
        )
    except Exception as exc:
        await audit_repository.record_event(
            build_marketing_evidence_audit_event(
                payload=evidence_payload,
                settings=settings,
                status="failed",
                failure_reason=str(exc),
            )
        )
        raise

    worker_run_id: str | None = None
    governance_run_id: str | None = None
    review_artifact_id: str | None = None
    synthesis_artifact_id: str | None = None

    if payload.run_mock_workers:
        worker_result = await run_marketing_worker_once(
            agent_bus_client=agent_bus_client,
            workflow_id=workflow.workflow_id,
            max_items=4,
        )
        worker_run_id = worker_result.worker_run_id

    if payload.run_mock_governance:
        governance_result = await run_marketing_governance_once(
            agent_bus_client=agent_bus_client,
            workflow_id=workflow.workflow_id,
            run_reviewer=True,
            run_hq_synthesis=True,
        )
        governance_run_id = governance_result.governance_run_id
        if governance_result.reviewer_result is not None:
            review_artifact_id = governance_result.reviewer_result.artifact_id
        if governance_result.hq_result is not None:
            synthesis_artifact_id = governance_result.hq_result.artifact_id

    return WeeklyMarketingSnapshotReadOnlyRunResponse(
        workflow_id=workflow.workflow_id,
        created_work_items=workflow.created_work_items,
        data_work_item_id=data_work_item_id,
        analytics_evidence_packet_id=evidence.evidence_packet_id,
        worker_run_id=worker_run_id,
        governance_run_id=governance_run_id,
        review_artifact_id=review_artifact_id,
        synthesis_artifact_id=synthesis_artifact_id,
        audit_events_url=f"/api/v1/marketing/evidence/audit?workflow_id={workflow.workflow_id}",
        summary_url=f"/api/v1/marketing/workflows/{workflow.workflow_id}/summary",
    )


def _preflight_optional_flags(payload: WeeklyMarketingSnapshotReadOnlyRunRequest, settings: Settings) -> None:
    if payload.run_mock_workers and not settings.enable_marketing_worker_mock:
        raise WeeklyMarketingSnapshotReadOnlyValidationError(
            "ENABLE_MARKETING_WORKER_MOCK=true is required when run_mock_workers=true."
        )
    if payload.run_mock_governance and not settings.enable_marketing_governance_mock:
        raise WeeklyMarketingSnapshotReadOnlyValidationError(
            "ENABLE_MARKETING_GOVERNANCE_MOCK=true is required when run_mock_governance=true."
        )
    if not settings.enable_marketing_sheets_readonly_evidence:
        raise WeeklyMarketingSnapshotReadOnlyValidationError(
            "ENABLE_MARKETING_SHEETS_READONLY_EVIDENCE=true is required for the weekly snapshot read-only wrapper."
        )


async def _find_data_work_item_id(
    agent_bus_client: WeeklyMarketingSnapshotAgentBusClient,
    workflow_id: str,
) -> str:
    work_items = await agent_bus_client.list_work_items(repository=MARKETING_REPOSITORY)
    for item in work_items:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if (
            metadata.get("workflow_id") == workflow_id
            and item.get("owner_agent") == HALL_DATA_AGENT
            and metadata.get("work_item_role") in {"specialist", "specialist_evidence"}
        ):
            value = item.get("work_item_id") or item.get("id")
            if value:
                return str(value)
    raise WeeklyMarketingSnapshotReadOnlyValidationError(
        f"Hall Data Intelligence work item was not found for workflow_id={workflow_id}."
    )
