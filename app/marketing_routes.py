from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status

from app.admin_auth import require_orchestrator_admin_token
from app.clients.agent_bus import AgentBusAPIError, AgentBusClient, MissingAgentBusBaseUrlError
from app.config import Settings, get_settings
from app.marketing_approval import (
    MarketingApprovalValidationError,
    get_marketing_mock_approval,
    record_marketing_mock_approval,
)
from app.marketing_approval_contract import MarketingApprovalRecord, MarketingApprovalRequest
from app.marketing_evidence_audit import (
    InMemoryMarketingEvidenceAuditRepository,
    JsonlMarketingEvidenceAuditRepository,
    MarketingEvidenceAuditRepository,
    audit_path_from_settings,
    build_marketing_evidence_audit_event,
)
from app.marketing_evidence_audit_contract import MarketingEvidenceAuditListResponse
from app.marketing_executive_brief_builder import build_weekly_marketing_executive_brief
from app.marketing_executive_brief_contract import MarketingExecutiveBriefResponse
from app.marketing_governance import MarketingGovernanceValidationError, run_marketing_governance_once
from app.marketing_governance_contract import MarketingGovernanceRunOnceRequest, MarketingGovernanceRunOnceResponse
from app.marketing_loop import (
    MockWeeklyMarketingBriefRequest,
    MockWeeklyMarketingBriefResponse,
    create_mock_weekly_marketing_command_brief,
)
from app.marketing_readonly_evidence import (
    MarketingReadOnlyEvidenceValidationError,
    attach_read_only_fixture_evidence,
)
from app.marketing_readonly_evidence_contract import (
    AttachReadOnlyFixtureEvidenceRequest,
    AttachReadOnlyFixtureEvidenceResponse,
)
from app.marketing_sheets_evidence_adapter import (
    ApprovedGoogleSheetsReadOnlySourceReader,
    MarketingSheetsEvidenceValidationError,
    MarketingSheetsSourceReadError,
    attach_google_sheets_readonly_evidence,
)
from app.marketing_sheets_evidence_contract import (
    AttachGoogleSheetsReadOnlyEvidenceRequest,
    AttachGoogleSheetsReadOnlyEvidenceResponse,
)
from app.marketing_summary import (
    MarketingWorkflowNotFoundError,
    MarketingWorkflowSummary,
    build_marketing_workflow_summary,
)
from app.marketing_worker import run_marketing_worker_once
from app.marketing_worker_contract import MarketingWorkerRunOnceRequest, MarketingWorkerRunOnceResponse
from app.weekly_marketing_snapshot_readonly import (
    WeeklyMarketingSnapshotReadOnlyValidationError,
    run_weekly_marketing_snapshot_readonly_workflow,
)
from app.weekly_marketing_snapshot_readonly_contract import (
    WeeklyMarketingSnapshotReadOnlyRunRequest,
    WeeklyMarketingSnapshotReadOnlyRunResponse,
)

router = APIRouter(prefix="/api/v1/marketing", tags=["marketing"])


@router.post(
    "/weekly-command-brief/mock-run",
    response_model=MockWeeklyMarketingBriefResponse,
)
async def mock_weekly_marketing_command_brief(
    payload: MockWeeklyMarketingBriefRequest,
    request: Request,
    _: None = Depends(require_orchestrator_admin_token),
    settings: Settings = Depends(get_settings),
) -> MockWeeklyMarketingBriefResponse:
    client, should_close = _agent_bus_client(request, settings)
    try:
        return await create_mock_weekly_marketing_command_brief(
            payload,
            agent_bus_client=client,
            mission_control_url=_mission_control_url(settings),
        )
    except MissingAgentBusBaseUrlError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AgentBusAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    finally:
        if should_close:
            await client.aclose()


@router.post(
    "/workflows/weekly-snapshot/read-only/run",
    response_model=WeeklyMarketingSnapshotReadOnlyRunResponse,
)
async def run_weekly_marketing_snapshot_readonly(
    payload: WeeklyMarketingSnapshotReadOnlyRunRequest,
    request: Request,
    _: None = Depends(require_orchestrator_admin_token),
    settings: Settings = Depends(get_settings),
) -> WeeklyMarketingSnapshotReadOnlyRunResponse:
    if not settings.enable_weekly_marketing_snapshot_readonly:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ENABLE_WEEKLY_MARKETING_SNAPSHOT_READONLY=true is required before running the weekly snapshot read-only wrapper.",
        )
    client, should_close = _agent_bus_client(request, settings)
    source_reader = getattr(request.app.state, "marketing_sheets_source_reader", None) or ApprovedGoogleSheetsReadOnlySourceReader(
        allowed_source_ids=settings.marketing_readonly_allowed_source_ids,
        credentials_path=settings.google_application_credentials,
    )
    try:
        return await run_weekly_marketing_snapshot_readonly_workflow(
            payload=payload,
            settings=settings,
            agent_bus_client=client,
            source_reader=source_reader,
            audit_repository=_marketing_evidence_audit_repository(request, settings),
            mission_control_url=_mission_control_url(settings),
        )
    except WeeklyMarketingSnapshotReadOnlyValidationError as exc:
        response_status = status.HTTP_403_FORBIDDEN if str(exc).startswith("ENABLE_") else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=response_status, detail=str(exc)) from exc
    except MarketingSheetsEvidenceValidationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MarketingSheetsSourceReadError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except MarketingGovernanceValidationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MissingAgentBusBaseUrlError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AgentBusAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    finally:
        if should_close:
            await client.aclose()


@router.post(
    "/workers/mock/run-once",
    response_model=MarketingWorkerRunOnceResponse,
)
async def run_mock_marketing_worker_once(
    payload: MarketingWorkerRunOnceRequest,
    request: Request,
    _: None = Depends(require_orchestrator_admin_token),
    settings: Settings = Depends(get_settings),
) -> MarketingWorkerRunOnceResponse:
    if not settings.enable_marketing_worker_mock:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ENABLE_MARKETING_WORKER_MOCK=true is required before running the mock marketing worker.",
        )
    client, should_close = _agent_bus_client(request, settings)
    try:
        return await run_marketing_worker_once(
            agent_bus_client=client,
            workflow_id=payload.workflow_id,
            max_items=payload.max_items,
        )
    except MissingAgentBusBaseUrlError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AgentBusAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    finally:
        if should_close:
            await client.aclose()


@router.post(
    "/evidence/read-only-fixture/attach",
    response_model=AttachReadOnlyFixtureEvidenceResponse,
)
async def attach_marketing_read_only_fixture_evidence(
    payload: AttachReadOnlyFixtureEvidenceRequest,
    request: Request,
    _: None = Depends(require_orchestrator_admin_token),
    settings: Settings = Depends(get_settings),
) -> AttachReadOnlyFixtureEvidenceResponse:
    if not settings.enable_marketing_readonly_evidence:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ENABLE_MARKETING_READONLY_EVIDENCE=true is required before attaching read-only fixture evidence.",
        )
    client, should_close = _agent_bus_client(request, settings)
    try:
        return await attach_read_only_fixture_evidence(
            agent_bus_client=client,
            payload=payload,
        )
    except MarketingReadOnlyEvidenceValidationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MissingAgentBusBaseUrlError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AgentBusAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    finally:
        if should_close:
            await client.aclose()


@router.post(
    "/evidence/google-sheets-readonly/attach",
    response_model=AttachGoogleSheetsReadOnlyEvidenceResponse,
)
async def attach_marketing_google_sheets_readonly_evidence(
    payload: AttachGoogleSheetsReadOnlyEvidenceRequest,
    request: Request,
    _: None = Depends(require_orchestrator_admin_token),
    settings: Settings = Depends(get_settings),
) -> AttachGoogleSheetsReadOnlyEvidenceResponse:
    audit_repository = _marketing_evidence_audit_repository(request, settings)
    client: AgentBusClient | None = None
    should_close = False
    try:
        if not settings.enable_marketing_sheets_readonly_evidence:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ENABLE_MARKETING_SHEETS_READONLY_EVIDENCE=true is required before attaching Google Sheets read-only evidence.",
            )
        client, should_close = _agent_bus_client(request, settings)
        source_reader = getattr(request.app.state, "marketing_sheets_source_reader", None) or ApprovedGoogleSheetsReadOnlySourceReader(
            allowed_source_ids=settings.marketing_readonly_allowed_source_ids,
            credentials_path=settings.google_application_credentials,
        )
        response = await attach_google_sheets_readonly_evidence(
            agent_bus_client=client,
            source_reader=source_reader,
            payload=payload,
        )
        await audit_repository.record_event(
            build_marketing_evidence_audit_event(
                payload=payload,
                settings=settings,
                status="success",
                evidence_packet_id=response.evidence_packet_id,
            )
        )
        return response
    except HTTPException as exc:
        await _record_failed_evidence_audit(audit_repository, payload, settings, _detail_text(exc.detail))
        raise
    except MarketingSheetsEvidenceValidationError as exc:
        await _record_failed_evidence_audit(audit_repository, payload, settings, str(exc))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MarketingSheetsSourceReadError as exc:
        await _record_failed_evidence_audit(audit_repository, payload, settings, str(exc))
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except MissingAgentBusBaseUrlError as exc:
        await _record_failed_evidence_audit(audit_repository, payload, settings, str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AgentBusAPIError as exc:
        await _record_failed_evidence_audit(audit_repository, payload, settings, str(exc))
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    finally:
        if should_close and client is not None:
            await client.aclose()


@router.get(
    "/evidence/audit",
    response_model=MarketingEvidenceAuditListResponse,
)
async def list_marketing_evidence_audit_events(
    request: Request,
    workflow_id: str | None = None,
    source_mode: str | None = None,
    event_status: str | None = Query(default=None, alias="status"),
    limit: int = 100,
    _: None = Depends(require_orchestrator_admin_token),
    settings: Settings = Depends(get_settings),
) -> MarketingEvidenceAuditListResponse:
    if not settings.enable_marketing_evidence_audit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ENABLE_MARKETING_EVIDENCE_AUDIT=false disables the marketing evidence audit read endpoint.",
        )
    repository = _marketing_evidence_audit_repository(request, settings)
    return MarketingEvidenceAuditListResponse(
        events=await repository.list_events(
            workflow_id=workflow_id,
            source_mode=source_mode,
            status=event_status,
            limit=limit,
        )
    )


@router.post(
    "/governance/mock/run-once",
    response_model=MarketingGovernanceRunOnceResponse,
)
async def run_mock_marketing_governance_once(
    payload: MarketingGovernanceRunOnceRequest,
    request: Request,
    _: None = Depends(require_orchestrator_admin_token),
    settings: Settings = Depends(get_settings),
) -> MarketingGovernanceRunOnceResponse:
    if not settings.enable_marketing_governance_mock:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ENABLE_MARKETING_GOVERNANCE_MOCK=true is required before running mock marketing governance.",
        )
    client, should_close = _agent_bus_client(request, settings)
    try:
        return await run_marketing_governance_once(
            agent_bus_client=client,
            workflow_id=payload.workflow_id,
            run_reviewer=payload.run_reviewer,
            run_hq_synthesis=payload.run_hq_synthesis,
        )
    except MarketingGovernanceValidationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MissingAgentBusBaseUrlError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AgentBusAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    finally:
        if should_close:
            await client.aclose()


@router.post(
    "/workflows/{workflow_id}/approval",
    response_model=MarketingApprovalRecord,
)
async def record_mock_marketing_approval(
    workflow_id: str,
    payload: MarketingApprovalRequest,
    request: Request,
    _: None = Depends(require_orchestrator_admin_token),
    settings: Settings = Depends(get_settings),
) -> MarketingApprovalRecord:
    if not settings.enable_marketing_approval_mock:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ENABLE_MARKETING_APPROVAL_MOCK=true is required before recording mock marketing approval.",
        )
    client, should_close = _agent_bus_client(request, settings)
    try:
        return await record_marketing_mock_approval(
            agent_bus_client=client,
            workflow_id=workflow_id,
            payload=payload,
        )
    except MarketingApprovalValidationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MissingAgentBusBaseUrlError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AgentBusAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    finally:
        if should_close:
            await client.aclose()


@router.get(
    "/workflows/{workflow_id}/approval",
    response_model=MarketingApprovalRecord,
)
async def get_mock_marketing_approval(
    workflow_id: str,
    request: Request,
    _: None = Depends(require_orchestrator_admin_token),
    settings: Settings = Depends(get_settings),
) -> MarketingApprovalRecord:
    client, should_close = _agent_bus_client(request, settings)
    try:
        return await get_marketing_mock_approval(
            agent_bus_client=client,
            workflow_id=workflow_id,
        )
    except MarketingApprovalValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MissingAgentBusBaseUrlError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AgentBusAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    finally:
        if should_close:
            await client.aclose()


@router.get(
    "/workflows/{workflow_id}/executive-brief",
    response_model=MarketingExecutiveBriefResponse,
)
async def marketing_workflow_executive_brief(
    workflow_id: str,
    request: Request,
    _: None = Depends(require_orchestrator_admin_token),
    settings: Settings = Depends(get_settings),
) -> MarketingExecutiveBriefResponse:
    if not settings.enable_weekly_marketing_executive_brief:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ENABLE_WEEKLY_MARKETING_EXECUTIVE_BRIEF=true is required before reading the weekly marketing executive brief.",
        )
    client, should_close = _agent_bus_client(request, settings)
    try:
        summary = await build_marketing_workflow_summary(
            workflow_id,
            agent_bus_client=client,
            agent_bus_mission_control_url=_mission_control_url(settings),
            orchestrator_snapshot_url=_orchestrator_snapshot_url(settings),
        )
        return build_weekly_marketing_executive_brief(_with_governance_next_action(summary))
    except MarketingWorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marketing workflow not found") from exc
    except MissingAgentBusBaseUrlError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "agent_bus_unavailable", "message": str(exc)},
        ) from exc
    except AgentBusAPIError as exc:
        response_status = status.HTTP_503_SERVICE_UNAVAILABLE if exc.status_code >= 500 else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(
            status_code=response_status,
            detail={"status": "agent_bus_unavailable", "message": str(exc)},
        ) from exc
    finally:
        if should_close:
            await client.aclose()


@router.get(
    "/workflows/{workflow_id}/summary",
    response_model=MarketingWorkflowSummary,
)
async def marketing_workflow_summary(
    workflow_id: str,
    request: Request,
    _: None = Depends(require_orchestrator_admin_token),
    settings: Settings = Depends(get_settings),
) -> MarketingWorkflowSummary:
    client, should_close = _agent_bus_client(request, settings)
    try:
        summary = await build_marketing_workflow_summary(
            workflow_id,
            agent_bus_client=client,
            agent_bus_mission_control_url=_mission_control_url(settings),
            orchestrator_snapshot_url=_orchestrator_snapshot_url(settings),
        )
        return _with_governance_next_action(summary)
    except MarketingWorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marketing workflow not found") from exc
    except MissingAgentBusBaseUrlError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "agent_bus_unavailable", "message": str(exc)},
        ) from exc
    except AgentBusAPIError as exc:
        response_status = status.HTTP_503_SERVICE_UNAVAILABLE if exc.status_code >= 500 else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(
            status_code=response_status,
            detail={"status": "agent_bus_unavailable", "message": str(exc)},
        ) from exc
    finally:
        if should_close:
            await client.aclose()


def register_marketing_routes(app: FastAPI) -> None:
    if getattr(app.state, "marketing_routes_registered", False):
        return
    app.include_router(router)
    app.state.marketing_routes_registered = True


def _agent_bus_client(request: Request, settings: Settings) -> tuple[AgentBusClient, bool]:
    client = getattr(request.app.state, "agent_bus_client", None)
    if client is not None:
        return client, False
    return (
        AgentBusClient(
            base_url=settings.agent_bus_base_url,
            token=settings.agent_bus_token,
            timeout_seconds=settings.agent_bus_timeout_seconds,
        ),
        True,
    )


def _marketing_evidence_audit_repository(request: Request, settings: Settings) -> MarketingEvidenceAuditRepository:
    repository = getattr(request.app.state, "marketing_evidence_audit_repository", None)
    if repository is not None:
        return repository
    audit_path = audit_path_from_settings(settings)
    if audit_path:
        repository = JsonlMarketingEvidenceAuditRepository(audit_path)
    else:
        repository = InMemoryMarketingEvidenceAuditRepository()
    request.app.state.marketing_evidence_audit_repository = repository
    return repository


async def _record_failed_evidence_audit(
    repository: MarketingEvidenceAuditRepository,
    payload: AttachGoogleSheetsReadOnlyEvidenceRequest,
    settings: Settings,
    failure_reason: str,
) -> None:
    await repository.record_event(
        build_marketing_evidence_audit_event(
            payload=payload,
            settings=settings,
            status="failed",
            failure_reason=failure_reason,
        )
    )


def _detail_text(detail: Any) -> str:
    return detail if isinstance(detail, str) else str(detail)


def _with_governance_next_action(summary: MarketingWorkflowSummary) -> MarketingWorkflowSummary:
    if getattr(summary, "human_approval", None) and summary.human_approval.state != "not_approved":
        return summary
    if "specialist_evidence" in summary.missing:
        summary.next_action = "Run the specialist worker before governance."
    elif "hq_synthesis_packet" in summary.missing and "review_packet" not in summary.missing:
        summary.next_action = "Run HQ synthesis."
    return summary


def _mission_control_url(settings: Settings) -> str:
    if settings.agent_bus_base_url:
        return f"{settings.agent_bus_base_url.rstrip('/')}/api/v1/mission-control/snapshot"
    return "/api/v1/mission-control/snapshot"


def _orchestrator_snapshot_url(settings: Settings) -> str:
    if settings.app_env == "local":
        return "http://127.0.0.1:8055/api/v1/orchestrator/snapshot"
    return "/api/v1/orchestrator/snapshot"
