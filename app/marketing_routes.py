from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status

from app.admin_auth import require_orchestrator_admin_token
from app.clients.agent_bus import AgentBusAPIError, AgentBusClient, MissingAgentBusBaseUrlError
from app.config import Settings, get_settings
from app.marketing_approval import (
    MarketingApprovalValidationError,
    get_marketing_mock_approval,
    record_marketing_mock_approval,
)
from app.marketing_approval_contract import MarketingApprovalRecord, MarketingApprovalRequest
from app.marketing_governance import MarketingGovernanceValidationError, run_marketing_governance_once
from app.marketing_governance_contract import MarketingGovernanceRunOnceRequest, MarketingGovernanceRunOnceResponse
from app.marketing_loop import (
    MockWeeklyMarketingBriefRequest,
    MockWeeklyMarketingBriefResponse,
    create_mock_weekly_marketing_command_brief,
)
from app.marketing_summary import (
    MarketingWorkflowNotFoundError,
    MarketingWorkflowSummary,
    build_marketing_workflow_summary,
)
from app.marketing_worker import run_marketing_worker_once
from app.marketing_worker_contract import MarketingWorkerRunOnceRequest, MarketingWorkerRunOnceResponse

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
