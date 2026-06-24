from __future__ import annotations

from typing import Any, Protocol
from uuid import uuid4

from app.clients.agent_bus import AgentBusAPIError
from app.marketing_agent_registry import get_marketing_agent
from app.marketing_loop import MARKETING_REPOSITORY, MARKETING_WORKFLOW_TYPE, MOCK_EVIDENCE_BY_AGENT, REVIEW_AGENT
from app.marketing_worker_contract import MarketingWorkerResult, MarketingWorkerRunOnceResponse

SPECIALIST_WORK_ITEM_ROLES = {"specialist", "specialist_evidence"}
PROCESSABLE_STATUSES = {"queued", "claimed", "awaiting_evidence", "in_progress"}


class MarketingWorkerError(Exception):
    pass


class MarketingWorkerValidationError(MarketingWorkerError):
    pass


class MarketingWorkerAgentBusClient(Protocol):
    async def list_work_items(self, *, repository: str | None = None) -> list[dict[str, Any]]: ...
    async def claim_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def transition_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def complete_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def create_evidence_packet(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def attach_evidence_to_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...


async def run_marketing_worker_once(
    *,
    agent_bus_client: MarketingWorkerAgentBusClient,
    workflow_id: str | None = None,
    max_items: int = 4,
) -> MarketingWorkerRunOnceResponse:
    worker_run_id = f"marketing-worker-run-{uuid4()}"
    work_items = await agent_bus_client.list_work_items(repository=MARKETING_REPOSITORY)
    eligible_items = [
        item
        for item in work_items
        if _is_eligible_marketing_specialist_item(item, workflow_id=workflow_id)
    ][:max_items]
    results: list[MarketingWorkerResult] = []
    for item in eligible_items:
        results.append(
            await process_marketing_specialist_work_item(
                item,
                agent_bus_client=agent_bus_client,
                worker_run_id=worker_run_id,
            )
        )
    return MarketingWorkerRunOnceResponse(
        worker_run_id=worker_run_id,
        workflow_id=workflow_id,
        processed=len([result for result in results if result.status == "completed"]),
        results=results,
    )


async def process_marketing_specialist_work_item(
    item: dict[str, Any],
    *,
    agent_bus_client: MarketingWorkerAgentBusClient,
    worker_run_id: str | None = None,
) -> MarketingWorkerResult:
    worker_run_id = worker_run_id or f"marketing-worker-run-{uuid4()}"
    metadata = _metadata(item)
    work_item_id = _work_item_id(item)
    agent_id = str(item.get("owner_agent") or metadata.get("specialist_agent") or "")
    workflow_id = _string_or_none(metadata.get("workflow_id"))
    _validate_specialist_item(item)

    await _claim_if_supported(agent_bus_client, work_item_id, agent_id)
    await _transition_if_supported(
        agent_bus_client,
        work_item_id,
        {"status": "in_progress", "actor": agent_id, "metadata": {"worker_run_id": worker_run_id}},
    )
    evidence_payload = _mock_specialist_evidence_payload(item, worker_run_id=worker_run_id)
    evidence = await agent_bus_client.create_evidence_packet(evidence_payload)
    evidence_packet_id = _response_id(evidence, "evidence_id")
    await agent_bus_client.attach_evidence_to_work_item(
        work_item_id,
        {"evidence_id": evidence_packet_id, "actor": agent_id},
    )
    await _complete_if_supported(
        agent_bus_client,
        work_item_id,
        {
            "actor": agent_id,
            "metadata": {
                "worker_run_id": worker_run_id,
                "worker_adapter": "marketing_mock_worker",
                "next_action": "ready_for_review",
            },
        },
    )
    return MarketingWorkerResult(
        worker_run_id=worker_run_id,
        workflow_id=workflow_id,
        agent_id=agent_id,
        work_item_id=work_item_id,
        status="completed",
        evidence_packet_id=evidence_packet_id,
        mock_mode=True,
        live_platform_access=False,
        next_action="ready_for_review",
    )


def _is_eligible_marketing_specialist_item(item: dict[str, Any], *, workflow_id: str | None) -> bool:
    metadata = _metadata(item)
    if workflow_id and metadata.get("workflow_id") != workflow_id:
        return False
    if metadata.get("domain") != "marketing":
        return False
    if metadata.get("workflow_type") != MARKETING_WORKFLOW_TYPE:
        return False
    if metadata.get("work_item_role") not in SPECIALIST_WORK_ITEM_ROLES:
        return False
    if _item_status(item) not in PROCESSABLE_STATUSES:
        return False
    if _evidence_ids(item):
        return False
    return _is_mock_only(metadata)


def _validate_specialist_item(item: dict[str, Any]) -> None:
    metadata = _metadata(item)
    work_item_id = _work_item_id(item)
    agent_id = str(item.get("owner_agent") or metadata.get("specialist_agent") or "")
    entry = get_marketing_agent(agent_id)
    if entry is None:
        raise MarketingWorkerValidationError(f"Unknown marketing agent for work item {work_item_id}: {agent_id}")
    if entry.agent_type != "marketing_specialist":
        raise MarketingWorkerValidationError(f"Agent is not a marketing specialist: {agent_id}")
    if entry.live_integrations_enabled:
        raise MarketingWorkerValidationError(f"Live integrations are not allowed for mock worker: {agent_id}")
    if metadata.get("domain") != "marketing":
        raise MarketingWorkerValidationError("Worker only processes marketing work items.")
    if metadata.get("workflow_type") != MARKETING_WORKFLOW_TYPE:
        raise MarketingWorkerValidationError("Unsupported marketing workflow type.")
    if metadata.get("work_item_role") not in SPECIALIST_WORK_ITEM_ROLES:
        raise MarketingWorkerValidationError("Worker only processes specialist work items.")
    if not _is_mock_only(metadata):
        raise MarketingWorkerValidationError("Worker refuses live-mode marketing work while live integrations are disabled.")
    evidence = MOCK_EVIDENCE_BY_AGENT.get(agent_id)
    if evidence is None:
        raise MarketingWorkerValidationError(f"No mock runner exists for marketing agent: {agent_id}")
    evidence_type = str(evidence.get("evidence_type") or "")
    if evidence_type not in entry.allowed_evidence_types:
        raise MarketingWorkerValidationError(f"Unsupported evidence type for {agent_id}: {evidence_type}")


def _mock_specialist_evidence_payload(item: dict[str, Any], *, worker_run_id: str) -> dict[str, Any]:
    metadata = _metadata(item)
    work_item_id = _work_item_id(item)
    agent_id = str(item.get("owner_agent") or metadata.get("specialist_agent") or "")
    evidence = MOCK_EVIDENCE_BY_AGENT[agent_id]
    return {
        "work_item_id": work_item_id,
        "repository": MARKETING_REPOSITORY,
        "implementation_agent": agent_id,
        "branch": "agent-integration",
        "commit_shas": [],
        "changed_files": [],
        "test_commands": ["marketing-worker-mock-run-once"],
        "test_results": {
            "mode": "mock_only",
            "mock_mode": True,
            "not_for_real_marketing_decisions": True,
            "worker_run_id": worker_run_id,
            "source_systems": evidence["sources_checked"],
            "live_platform_access": False,
            "evidence_schema": "marketing.worker_mock_evidence.v1",
            "marketing_metadata": metadata,
            **evidence,
        },
        "verification_summary": evidence["summary"],
        "assumptions": ["No live marketing platform data was used."],
        "unverified_items": ["Mock evidence is not for real marketing decisions."],
    }


async def _claim_if_supported(client: MarketingWorkerAgentBusClient, work_item_id: str, agent_id: str) -> None:
    try:
        await client.claim_work_item(work_item_id, {"agent_id": agent_id})
    except AgentBusAPIError as exc:
        if exc.status_code not in {404, 405, 409, 501}:
            raise


async def _transition_if_supported(client: MarketingWorkerAgentBusClient, work_item_id: str, payload: dict[str, Any]) -> None:
    try:
        await client.transition_work_item(work_item_id, payload)
    except AgentBusAPIError as exc:
        if exc.status_code not in {404, 405, 409, 501}:
            raise


async def _complete_if_supported(client: MarketingWorkerAgentBusClient, work_item_id: str, payload: dict[str, Any]) -> None:
    try:
        await client.complete_work_item(work_item_id, payload)
    except AgentBusAPIError as exc:
        if exc.status_code not in {404, 405, 409, 501}:
            raise
        await _transition_if_supported(
            client,
            work_item_id,
            {"status": "ready_for_review", "actor": payload["actor"], "metadata": payload.get("metadata", {})},
        )


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _work_item_id(item: dict[str, Any]) -> str:
    value = item.get("work_item_id") or item.get("id")
    if not value:
        raise MarketingWorkerValidationError("Agent Bus work item did not include work_item_id.")
    return str(value)


def _item_status(item: dict[str, Any]) -> str:
    return str(item.get("status") or "unknown")


def _evidence_ids(item: dict[str, Any]) -> list[str]:
    raw_ids = _metadata(item).get("evidence_packet_ids", [])
    if not isinstance(raw_ids, list):
        return []
    return [str(value) for value in raw_ids if value]


def _is_mock_only(metadata: dict[str, Any]) -> bool:
    if metadata.get("live_platform_access") is not False:
        return False
    return metadata.get("mock_mode") is True or metadata.get("mvp_mode") == "mock_only"


def _response_id(response: dict[str, Any], key: str) -> str:
    value = response.get(key) or response.get("id")
    if not value:
        raise MarketingWorkerValidationError(f"Agent Bus response did not include {key}.")
    return str(value)


def _string_or_none(value: Any) -> str | None:
    return str(value) if value is not None else None
