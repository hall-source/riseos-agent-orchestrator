from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status

from app.admin_auth import require_orchestrator_admin_token
from app.clients.agent_bus import AgentBusAPIError, AgentBusClient, MissingAgentBusBaseUrlError
from app.config import Settings, get_settings
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
        return await build_marketing_workflow_summary(
            workflow_id,
            agent_bus_client=client,
            agent_bus_mission_control_url=_mission_control_url(settings),
            orchestrator_snapshot_url=_orchestrator_snapshot_url(settings),
        )
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


def _mission_control_url(settings: Settings) -> str:
    if settings.agent_bus_base_url:
        return f"{settings.agent_bus_base_url.rstrip('/')}/api/v1/mission-control/snapshot"
    return "/api/v1/mission-control/snapshot"


def _orchestrator_snapshot_url(settings: Settings) -> str:
    if settings.app_env == "local":
        return "http://127.0.0.1:8055/api/v1/orchestrator/snapshot"
    return "/api/v1/orchestrator/snapshot"
