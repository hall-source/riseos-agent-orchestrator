from __future__ import annotations

from typing import Any, Protocol
from uuid import uuid4

from app.clients.agent_bus import AgentBusAPIError
from app.marketing_governance_contract import MarketingGovernanceRunOnceResponse, MarketingGovernanceStageResult
from app.marketing_loop import (
    MARKETING_REPOSITORY,
    MARKETING_SOURCE_EVENT,
    MARKETING_WORKFLOW_TYPE,
    REVIEW_AGENT,
    SPECIALIST_AGENTS,
    SYNTHESIS_AGENT,
)

REVIEW_ARTIFACT_TYPE = "risk_review"
SYNTHESIS_ARTIFACT_TYPE = "synthesis_memo"
SPECIALIST_WORK_ITEM_ROLES = {"specialist", "specialist_evidence"}
HALL_REVIEW_NEXT_ACTION = "Hall can review the mock HQ synthesis memo. No production action is allowed from mock evidence."


class MarketingGovernanceError(Exception):
    pass


class MarketingGovernanceValidationError(MarketingGovernanceError):
    pass


class MarketingGovernanceAgentBusClient(Protocol):
    async def list_work_items(self, *, repository: str | None = None) -> list[dict[str, Any]]: ...
    async def create_work_item(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def transition_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def complete_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def create_evidence_packet(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def get_evidence_packet(self, evidence_id: str) -> dict[str, Any]: ...
    async def attach_evidence_to_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...


async def run_marketing_governance_once(
    *,
    agent_bus_client: MarketingGovernanceAgentBusClient,
    workflow_id: str,
    run_reviewer: bool = True,
    run_hq_synthesis: bool = True,
) -> MarketingGovernanceRunOnceResponse:
    governance_run_id = f"marketing-governance-run-{uuid4()}"
    work_items = await _workflow_work_items(agent_bus_client, workflow_id)
    representative_metadata = _representative_metadata(work_items)
    specialist_items = _specialist_items(work_items)
    specialist_evidence_packets = await _required_specialist_evidence_packets(
        agent_bus_client,
        specialist_items,
    )
    specialist_evidence_ids = [_artifact_id(packet) for packet in specialist_evidence_packets]
    reviewer_result: MarketingGovernanceStageResult | None = None
    hq_result: MarketingGovernanceStageResult | None = None
    review_artifact_id: str | None = None

    if run_reviewer:
        reviewer_item = await _ensure_governance_work_item(
            agent_bus_client,
            work_items,
            agent_id=REVIEW_AGENT,
            role="marketing_review",
            title="Mock marketing reviewer: Weekly Marketing Command Brief",
            workflow_id=workflow_id,
            representative_metadata=representative_metadata,
            depends_on_work_item_ids=[_work_item_id(item) for item in specialist_items.values()],
        )
        work_items = await _workflow_work_items(agent_bus_client, workflow_id)
        existing_review = await _existing_artifact_for_item(
            agent_bus_client,
            reviewer_item,
            REVIEW_ARTIFACT_TYPE,
        )
        if existing_review is None:
            existing_review = await _create_review_artifact(
                agent_bus_client,
                reviewer_item,
                workflow_id=workflow_id,
                governance_run_id=governance_run_id,
                representative_metadata=representative_metadata,
                specialist_evidence_ids=specialist_evidence_ids,
            )
        review_artifact_id = _artifact_id(existing_review)
        reviewer_result = MarketingGovernanceStageResult(
            status="completed",
            work_item_id=_work_item_id(reviewer_item),
            artifact_id=review_artifact_id,
            artifact_type=REVIEW_ARTIFACT_TYPE,
        )
        await _complete_if_supported(
            agent_bus_client,
            _work_item_id(reviewer_item),
            {
                "actor": REVIEW_AGENT,
                "metadata": {
                    "governance_run_id": governance_run_id,
                    "review_artifact_id": review_artifact_id,
                    "review_packet_created": True,
                    "next_action": "run_hq_synthesis",
                },
            },
        )
    else:
        reviewer_item = _item_for_agent(work_items, REVIEW_AGENT, role="marketing_review")
        existing_review = await _existing_artifact_for_item(agent_bus_client, reviewer_item, REVIEW_ARTIFACT_TYPE)
        review_artifact_id = _artifact_id(existing_review) if existing_review else None
        reviewer_result = MarketingGovernanceStageResult(
            status="skipped",
            work_item_id=_work_item_id_or_none(reviewer_item),
            artifact_id=review_artifact_id,
            artifact_type=REVIEW_ARTIFACT_TYPE if review_artifact_id else None,
            skipped_reason="run_reviewer=false",
        )

    if run_hq_synthesis:
        if not review_artifact_id:
            raise MarketingGovernanceValidationError("Run reviewer before HQ synthesis.")
        work_items = await _workflow_work_items(agent_bus_client, workflow_id)
        hq_item = await _ensure_governance_work_item(
            agent_bus_client,
            work_items,
            agent_id=SYNTHESIS_AGENT,
            role="hq_synthesis",
            title="Mock Clone Banks HQ synthesis: Weekly Marketing Command Brief",
            workflow_id=workflow_id,
            representative_metadata=representative_metadata,
            depends_on_work_item_ids=[_work_item_id(item) for item in specialist_items.values()],
        )
        existing_synthesis = await _existing_artifact_for_item(
            agent_bus_client,
            hq_item,
            SYNTHESIS_ARTIFACT_TYPE,
        )
        if existing_synthesis is None:
            existing_synthesis = await _create_synthesis_artifact(
                agent_bus_client,
                hq_item,
                workflow_id=workflow_id,
                governance_run_id=governance_run_id,
                representative_metadata=representative_metadata,
                specialist_evidence_ids=specialist_evidence_ids,
                review_artifact_id=review_artifact_id,
            )
        synthesis_artifact_id = _artifact_id(existing_synthesis)
        hq_result = MarketingGovernanceStageResult(
            status="completed",
            work_item_id=_work_item_id(hq_item),
            artifact_id=synthesis_artifact_id,
            artifact_type=SYNTHESIS_ARTIFACT_TYPE,
        )
        await _complete_if_supported(
            agent_bus_client,
            _work_item_id(hq_item),
            {
                "actor": SYNTHESIS_AGENT,
                "metadata": {
                    "governance_run_id": governance_run_id,
                    "synthesis_artifact_id": synthesis_artifact_id,
                    "synthesis_memo_created": True,
                    "next_action": "human_review",
                },
            },
        )
    else:
        hq_item = _item_for_agent(work_items, SYNTHESIS_AGENT, role="hq_synthesis")
        existing_synthesis = await _existing_artifact_for_item(agent_bus_client, hq_item, SYNTHESIS_ARTIFACT_TYPE)
        hq_result = MarketingGovernanceStageResult(
            status="skipped",
            work_item_id=_work_item_id_or_none(hq_item),
            artifact_id=_artifact_id(existing_synthesis) if existing_synthesis else None,
            artifact_type=SYNTHESIS_ARTIFACT_TYPE if existing_synthesis else None,
            skipped_reason="run_hq_synthesis=false",
        )

    return MarketingGovernanceRunOnceResponse(
        governance_run_id=governance_run_id,
        workflow_id=workflow_id,
        reviewer_result=reviewer_result,
        hq_result=hq_result,
        mock_mode=True,
        live_platform_access=False,
        next_action=_next_action(reviewer_result, hq_result),
    )


async def _workflow_work_items(
    client: MarketingGovernanceAgentBusClient,
    workflow_id: str,
) -> list[dict[str, Any]]:
    work_items = [
        item
        for item in await client.list_work_items(repository=MARKETING_REPOSITORY)
        if _metadata(item).get("workflow_id") == workflow_id
    ]
    if not work_items:
        raise MarketingGovernanceValidationError(f"No marketing work items found for workflow_id={workflow_id}.")
    return work_items


def _specialist_items(work_items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for agent_id in SPECIALIST_AGENTS:
        item = _item_for_agent(work_items, agent_id, roles=SPECIALIST_WORK_ITEM_ROLES)
        if item is not None:
            found[agent_id] = item
    missing_agents = [agent_id for agent_id in SPECIALIST_AGENTS if agent_id not in found]
    if missing_agents:
        raise MarketingGovernanceValidationError(
            "Run the specialist worker before governance. Missing specialist work items: " + ", ".join(missing_agents)
        )
    return found


async def _required_specialist_evidence_packets(
    client: MarketingGovernanceAgentBusClient,
    specialist_items: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    missing_evidence_agents: list[str] = []
    for agent_id, item in specialist_items.items():
        evidence_ids = _evidence_ids(item)
        if not evidence_ids:
            missing_evidence_agents.append(agent_id)
            continue
        for evidence_id in evidence_ids:
            packet = await client.get_evidence_packet(evidence_id)
            _validate_mock_evidence_packet(packet, agent_id=agent_id)
            packets.append(packet)
    if missing_evidence_agents:
        raise MarketingGovernanceValidationError(
            "Run the specialist worker before governance. Missing specialist evidence for: "
            + ", ".join(missing_evidence_agents)
        )
    return packets


def _validate_mock_evidence_packet(packet: dict[str, Any], *, agent_id: str) -> None:
    content = _artifact_content(packet)
    if content.get("live_platform_access") is not False:
        raise MarketingGovernanceValidationError(f"Specialist evidence for {agent_id} is not marked live_platform_access=false.")
    if content.get("confidence") != "mock_only" and content.get("mode") != "mock_only":
        raise MarketingGovernanceValidationError(f"Specialist evidence for {agent_id} is not marked mock_only.")


async def _ensure_governance_work_item(
    client: MarketingGovernanceAgentBusClient,
    work_items: list[dict[str, Any]],
    *,
    agent_id: str,
    role: str,
    title: str,
    workflow_id: str,
    representative_metadata: dict[str, Any],
    depends_on_work_item_ids: list[str],
) -> dict[str, Any]:
    existing = _item_for_agent(work_items, agent_id, role=role)
    if existing is not None:
        return existing
    payload = {
        "title": title,
        "repository": MARKETING_REPOSITORY,
        "description": "Mock-only marketing governance stage. No live systems or real agents are called.",
        "priority": "normal",
        "owner_agent": agent_id,
        "review_agent": REVIEW_AGENT,
        "metadata": {
            "domain": "marketing",
            "brand": representative_metadata.get("brand") or "rise",
            "business_unit": representative_metadata.get("business_unit") or "RISE Commercial District",
            "workflow_id": workflow_id,
            "workflow_type": MARKETING_WORKFLOW_TYPE,
            "source_event": representative_metadata.get("source_event") or MARKETING_SOURCE_EVENT,
            "work_item_role": role,
            "requested_by": representative_metadata.get("requested_by") or "Hall",
            "human_owner": representative_metadata.get("human_owner") or "Hall",
            "depends_on_work_item_ids": depends_on_work_item_ids,
            "mock_mode": True,
            "mvp_mode": "mock_only",
            "live_platform_access": False,
            "approval_required": True,
            "human_approval_required": True,
            "not_for_real_marketing_decisions": True,
        },
    }
    return await client.create_work_item(payload)


async def _create_review_artifact(
    client: MarketingGovernanceAgentBusClient,
    item: dict[str, Any],
    *,
    workflow_id: str,
    governance_run_id: str,
    representative_metadata: dict[str, Any],
    specialist_evidence_ids: list[str],
) -> dict[str, Any]:
    content = {
        "artifact_type": REVIEW_ARTIFACT_TYPE,
        "evidence_type": REVIEW_ARTIFACT_TYPE,
        "produced_by": REVIEW_AGENT,
        "workflow_type": MARKETING_WORKFLOW_TYPE,
        "workflow_id": workflow_id,
        "summary": "Mock reviewer validated that specialist mock evidence exists and is safe for workflow testing.",
        "checked": [
            "required specialist work items exist",
            "specialist evidence packets exist",
            "all evidence is marked mock_only",
            "live_platform_access is false",
            "no production actions are requested",
            "human approval remains required",
        ],
        "referenced_evidence_packet_ids": specialist_evidence_ids,
        "risk_flags": [
            "mock_only_no_business_decisions",
            "requires_real_data_before_operational_use",
        ],
        "approval_recommendation": "ready_for_hq_synthesis_mock_only",
        "mock_mode": True,
        "confidence": "mock_only",
        "live_platform_access": False,
        "not_for_real_marketing_decisions": True,
        "human_approval_required": True,
        "marketing_metadata": representative_metadata,
        "governance_run_id": governance_run_id,
    }
    return await _create_and_attach_artifact(
        client,
        item,
        actor=REVIEW_AGENT,
        content=content,
        verification_summary=content["summary"],
    )


async def _create_synthesis_artifact(
    client: MarketingGovernanceAgentBusClient,
    item: dict[str, Any],
    *,
    workflow_id: str,
    governance_run_id: str,
    representative_metadata: dict[str, Any],
    specialist_evidence_ids: list[str],
    review_artifact_id: str,
) -> dict[str, Any]:
    content = {
        "artifact_type": SYNTHESIS_ARTIFACT_TYPE,
        "evidence_type": SYNTHESIS_ARTIFACT_TYPE,
        "produced_by": SYNTHESIS_AGENT,
        "workflow_type": MARKETING_WORKFLOW_TYPE,
        "workflow_id": workflow_id,
        "summary": "Mock Weekly Marketing Command Brief synthesized from worker-produced mock specialist evidence and mock reviewer packet.",
        "referenced_evidence_packet_ids": specialist_evidence_ids,
        "referenced_review_artifact_id": review_artifact_id,
        "wins": [
            "Specialist worker adapter completed mock specialist work.",
            "Specialist evidence packets were attached successfully.",
            "Reviewer and HQ stages executed after specialist evidence existed.",
        ],
        "losses": [
            "No live marketing data was used.",
            "No real ChatGPT specialist agents were executed.",
        ],
        "opportunities": [
            "Next step is to test one read-only real data source.",
            "Future agent execution can replace deterministic mock runners.",
        ],
        "risks": [
            "Do not use mock evidence for real marketing decisions.",
            "Do not connect production tools until approval boundaries are validated.",
        ],
        "recommended_actions": [
            "Approve continued development toward read-only data-source evidence.",
            "Keep write actions disabled.",
        ],
        "approval_status": "awaiting_human_approval_mock_only",
        "mock_mode": True,
        "confidence": "mock_only",
        "live_platform_access": False,
        "not_for_real_marketing_decisions": True,
        "human_approval_required": True,
        "marketing_metadata": representative_metadata,
        "governance_run_id": governance_run_id,
    }
    return await _create_and_attach_artifact(
        client,
        item,
        actor=SYNTHESIS_AGENT,
        content=content,
        verification_summary=content["summary"],
    )


async def _create_and_attach_artifact(
    client: MarketingGovernanceAgentBusClient,
    item: dict[str, Any],
    *,
    actor: str,
    content: dict[str, Any],
    verification_summary: str,
) -> dict[str, Any]:
    packet = await client.create_evidence_packet(
        {
            "work_item_id": _work_item_id(item),
            "repository": MARKETING_REPOSITORY,
            "implementation_agent": actor,
            "branch": "agent-integration",
            "commit_shas": [],
            "changed_files": [],
            "test_commands": ["marketing-governance-mock-run-once"],
            "test_results": content,
            "verification_summary": verification_summary,
            "assumptions": ["No live marketing platform data was used."],
            "unverified_items": ["Mock governance artifacts are not for real marketing decisions."],
        }
    )
    artifact_id = _artifact_id(packet)
    await client.attach_evidence_to_work_item(_work_item_id(item), {"evidence_id": artifact_id, "actor": actor})
    return packet


async def _existing_artifact_for_item(
    client: MarketingGovernanceAgentBusClient,
    item: dict[str, Any] | None,
    artifact_type: str,
) -> dict[str, Any] | None:
    if item is None:
        return None
    for evidence_id in _evidence_ids(item):
        packet = await client.get_evidence_packet(evidence_id)
        if _artifact_type(packet) == artifact_type:
            return packet
    return None


async def _complete_if_supported(client: MarketingGovernanceAgentBusClient, work_item_id: str, payload: dict[str, Any]) -> None:
    try:
        await client.complete_work_item(work_item_id, payload)
    except AgentBusAPIError as exc:
        if exc.status_code not in {404, 405, 409, 501}:
            raise
        await _transition_if_supported(
            client,
            work_item_id,
            {"status": "completed", "actor": payload["actor"], "metadata": payload.get("metadata", {})},
        )


async def _transition_if_supported(client: MarketingGovernanceAgentBusClient, work_item_id: str, payload: dict[str, Any]) -> None:
    try:
        await client.transition_work_item(work_item_id, payload)
    except AgentBusAPIError as exc:
        if exc.status_code not in {404, 405, 409, 501}:
            raise


def _item_for_agent(
    work_items: list[dict[str, Any]],
    agent_id: str,
    *,
    role: str | None = None,
    roles: set[str] | None = None,
) -> dict[str, Any] | None:
    allowed_roles = roles if roles is not None else ({role} if role is not None else set())
    matching = [
        item
        for item in work_items
        if item.get("owner_agent") == agent_id
        and (not allowed_roles or _metadata(item).get("work_item_role") in allowed_roles)
    ]
    if not matching:
        return None
    return sorted(matching, key=lambda item: str(item.get("created_at") or ""))[0]


def _representative_metadata(work_items: list[dict[str, Any]]) -> dict[str, Any]:
    for item in work_items:
        metadata = _metadata(item)
        if metadata.get("workflow_type") == MARKETING_WORKFLOW_TYPE:
            return metadata
    return _metadata(work_items[0])


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _evidence_ids(item: dict[str, Any]) -> list[str]:
    raw_ids = _metadata(item).get("evidence_packet_ids", [])
    if not isinstance(raw_ids, list):
        return []
    return [str(value) for value in raw_ids if value]


def _artifact_content(packet: dict[str, Any] | None) -> dict[str, Any]:
    if packet is None:
        return {}
    test_results = packet.get("test_results")
    return test_results if isinstance(test_results, dict) else {}


def _artifact_type(packet: dict[str, Any] | None) -> str | None:
    if packet is None:
        return None
    content = _artifact_content(packet)
    value = content.get("artifact_type") or content.get("evidence_type") or packet.get("type")
    return str(value) if value else None


def _artifact_id(packet: dict[str, Any]) -> str:
    value = packet.get("evidence_id") or packet.get("id")
    if not value:
        raise MarketingGovernanceValidationError("Agent Bus artifact response did not include evidence_id.")
    return str(value)


def _work_item_id(item: dict[str, Any]) -> str:
    value = item.get("work_item_id") or item.get("id")
    if not value:
        raise MarketingGovernanceValidationError("Agent Bus work item did not include work_item_id.")
    return str(value)


def _work_item_id_or_none(item: dict[str, Any] | None) -> str | None:
    return _work_item_id(item) if item is not None else None


def _next_action(
    reviewer_result: MarketingGovernanceStageResult | None,
    hq_result: MarketingGovernanceStageResult | None,
) -> str:
    if reviewer_result is None or reviewer_result.status != "completed":
        return "Run marketing reviewer."
    if hq_result is None or hq_result.status != "completed":
        return "Run HQ synthesis."
    return HALL_REVIEW_NEXT_ACTION
