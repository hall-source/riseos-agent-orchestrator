from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.marketing_loop import (
    MARKETING_REPOSITORY,
    MARKETING_SOURCE_EVENT,
    MARKETING_WORKFLOW_TYPE,
    REVIEW_AGENT,
    SPECIALIST_AGENTS,
    SYNTHESIS_AGENT,
)

BLOCKED_STATUSES = {"blocked", "failed", "rejected"}
COMPLETE_STATUSES = {"approved", "completed"}
ACTIVE_STATUSES = {"claimed", "in_progress", "awaiting_evidence", "ready_for_review", "review_in_progress"}
REVIEW_ARTIFACT_TYPE = "risk_review"
SYNTHESIS_ARTIFACT_TYPE = "synthesis_memo"


class MarketingSummaryAgent(BaseModel):
    agent_id: str
    role: str
    status: str
    work_item_id: str | None = None
    evidence_count: int = 0
    evidence_types: list[str] = Field(default_factory=list)


class MarketingReviewSummary(BaseModel):
    review_agent: str
    work_item_id: str | None = None
    status: str
    artifact_type: str | None = None
    artifact_id: str | None = None
    review_packet_ids: list[str] = Field(default_factory=list)
    approval_recommendation: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    ready: bool = False


class MarketingSynthesisSummary(BaseModel):
    agent_id: str
    work_item_id: str | None = None
    status: str
    artifact_type: str | None = None
    artifact_id: str | None = None
    approval_status: str | None = None
    summary: str | None = None
    ready: bool = False


class MarketingReadinessSummary(BaseModel):
    specialist_evidence_complete: bool = False
    review_complete: bool = False
    synthesis_complete: bool = False
    human_approval_ready: bool = False


class MarketingWorkflowSummaryLinks(BaseModel):
    agent_bus_mission_control: str
    orchestrator_snapshot: str


class MarketingWorkflowSummary(BaseModel):
    workflow_id: str
    workflow_type: str = MARKETING_WORKFLOW_TYPE
    domain: str = "marketing"
    brand: str = "rise"
    business_unit: str = "RISE Commercial District"
    source_event: str = MARKETING_SOURCE_EVENT
    status: str = "unknown"
    requested_by: str = "Hall"
    human_owner: str = "Hall"
    approval_required: bool = True
    created_at: str | None = None
    updated_at: str | None = None
    agents: list[MarketingSummaryAgent] = Field(default_factory=list)
    specialist_work_items: list[dict[str, Any]] = Field(default_factory=list)
    evidence_packets: list[dict[str, Any]] = Field(default_factory=list)
    review: MarketingReviewSummary
    synthesis: MarketingSynthesisSummary
    readiness: MarketingReadinessSummary
    missing: list[str] = Field(default_factory=list)
    next_action: str
    links: MarketingWorkflowSummaryLinks


class MarketingSummaryAgentBusClient(Protocol):
    async def list_work_items(self, *, repository: str | None = None) -> list[dict[str, Any]]: ...
    async def get_evidence_packet(self, evidence_id: str) -> dict[str, Any]: ...


class MarketingWorkflowNotFoundError(Exception):
    pass


async def build_marketing_workflow_summary(
    workflow_id: str,
    *,
    agent_bus_client: MarketingSummaryAgentBusClient,
    agent_bus_mission_control_url: str,
    orchestrator_snapshot_url: str,
) -> MarketingWorkflowSummary:
    work_items = [
        item
        for item in await agent_bus_client.list_work_items(repository=MARKETING_REPOSITORY)
        if _metadata(item).get("workflow_id") == workflow_id
    ]
    if not work_items:
        raise MarketingWorkflowNotFoundError(workflow_id)

    evidence_packets = await _load_evidence_packets(agent_bus_client, work_items)
    evidence_by_work_item = _evidence_by_work_item(evidence_packets)
    specialist_items = [_item_for_agent(work_items, agent_id, role="specialist_evidence") for agent_id in SPECIALIST_AGENTS]
    review_item = _item_for_agent(work_items, REVIEW_AGENT, role="marketing_review")
    synthesis_item = _item_for_agent(work_items, SYNTHESIS_AGENT, role="hq_synthesis")
    review_artifact = _artifact_packet_for_item(review_item, evidence_by_work_item, REVIEW_ARTIFACT_TYPE)
    synthesis_artifact = _artifact_packet_for_item(synthesis_item, evidence_by_work_item, SYNTHESIS_ARTIFACT_TYPE)
    review_content = _artifact_content(review_artifact)
    synthesis_content = _artifact_content(synthesis_artifact)
    representative_metadata = _representative_metadata(work_items)

    agents = [
        _agent_summary(agent_id, "specialist", specialist_items[index], evidence_by_work_item)
        for index, agent_id in enumerate(SPECIALIST_AGENTS)
    ]
    agents.append(_agent_summary(REVIEW_AGENT, "review", review_item, evidence_by_work_item))
    agents.append(_agent_summary(SYNTHESIS_AGENT, "synthesis", synthesis_item, evidence_by_work_item))

    specialist_evidence_complete = all(
        item is not None and _evidence_count(item, evidence_by_work_item) > 0
        for item in specialist_items
    )
    review_complete = review_artifact is not None or _review_metadata_complete(review_item)
    synthesis_complete = synthesis_artifact is not None or _synthesis_metadata_complete(synthesis_item)
    human_approved = _human_approved(work_items)
    approval_required = bool(representative_metadata.get("approval_required", True))
    readiness = MarketingReadinessSummary(
        specialist_evidence_complete=specialist_evidence_complete,
        review_complete=review_complete,
        synthesis_complete=synthesis_complete,
        human_approval_ready=bool(
            approval_required
            and specialist_evidence_complete
            and review_complete
            and synthesis_complete
            and not human_approved
        ),
    )
    missing = _missing_items(readiness, approval_required=approval_required, human_approved=human_approved)
    status = _workflow_status(work_items, readiness, approval_required=approval_required, human_approved=human_approved)

    return MarketingWorkflowSummary(
        workflow_id=workflow_id,
        workflow_type=str(representative_metadata.get("workflow_type") or MARKETING_WORKFLOW_TYPE),
        domain=str(representative_metadata.get("domain") or "marketing"),
        brand=str(representative_metadata.get("brand") or "rise"),
        business_unit=str(representative_metadata.get("business_unit") or "RISE Commercial District"),
        source_event=str(representative_metadata.get("source_event") or MARKETING_SOURCE_EVENT),
        status=status,
        requested_by=str(representative_metadata.get("requested_by") or "Hall"),
        human_owner=str(representative_metadata.get("human_owner") or "Hall"),
        approval_required=approval_required,
        created_at=_min_timestamp(work_items, "created_at"),
        updated_at=_max_timestamp(work_items, "updated_at"),
        agents=agents,
        specialist_work_items=[item for item in specialist_items if item is not None],
        evidence_packets=evidence_packets,
        review=MarketingReviewSummary(
            review_agent=REVIEW_AGENT,
            work_item_id=_work_item_id(review_item),
            status=_artifact_status(review_item, review_artifact),
            artifact_type=_artifact_type(review_artifact),
            artifact_id=_artifact_id(review_artifact),
            review_packet_ids=_review_packet_ids(review_item),
            approval_recommendation=_string_or_none(review_content.get("approval_recommendation")),
            risk_flags=_string_list(review_content.get("risk_flags")),
            evidence_count=_evidence_count(review_item, evidence_by_work_item),
            ready=review_complete,
        ),
        synthesis=MarketingSynthesisSummary(
            agent_id=SYNTHESIS_AGENT,
            work_item_id=_work_item_id(synthesis_item),
            status=_artifact_status(synthesis_item, synthesis_artifact),
            artifact_type=_artifact_type(synthesis_artifact),
            artifact_id=_artifact_id(synthesis_artifact),
            approval_status=_string_or_none(synthesis_content.get("approval_status")),
            summary=_string_or_none(synthesis_content.get("summary")),
            ready=synthesis_complete,
        ),
        readiness=readiness,
        missing=missing,
        next_action=_next_action(status, missing, readiness),
        links=MarketingWorkflowSummaryLinks(
            agent_bus_mission_control=agent_bus_mission_control_url,
            orchestrator_snapshot=orchestrator_snapshot_url,
        ),
    )


async def _load_evidence_packets(
    client: MarketingSummaryAgentBusClient,
    work_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence_packets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in work_items:
        for evidence_id in _evidence_ids(item):
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            evidence_packets.append(await client.get_evidence_packet(evidence_id))
    return evidence_packets


def _agent_summary(
    agent_id: str,
    role: str,
    item: dict[str, Any] | None,
    evidence_by_work_item: dict[str, list[dict[str, Any]]],
) -> MarketingSummaryAgent:
    evidence_types = _evidence_types(item, evidence_by_work_item)
    return MarketingSummaryAgent(
        agent_id=agent_id,
        role=role,
        status=_agent_status(role, item, len(evidence_types)),
        work_item_id=_work_item_id(item),
        evidence_count=_evidence_count(item, evidence_by_work_item),
        evidence_types=evidence_types,
    )


def _agent_status(role: str, item: dict[str, Any] | None, evidence_type_count: int) -> str:
    status = _item_status(item)
    if item is None:
        return "missing"
    if status in BLOCKED_STATUSES:
        return "blocked"
    if status in COMPLETE_STATUSES:
        return "completed"
    if role in {"specialist", "review", "synthesis"} and evidence_type_count > 0:
        return "completed"
    if status in ACTIVE_STATUSES or status == "queued":
        return "in_progress"
    return status or "unknown"


def _workflow_status(
    work_items: list[dict[str, Any]],
    readiness: MarketingReadinessSummary,
    *,
    approval_required: bool,
    human_approved: bool,
) -> str:
    statuses = {_item_status(item) for item in work_items}
    if statuses & BLOCKED_STATUSES:
        return "blocked"
    if approval_required and human_approved:
        return "completed"
    if not approval_required and readiness.review_complete and readiness.synthesis_complete:
        return "completed"
    if readiness.human_approval_ready:
        return "awaiting_human_approval"
    if readiness.specialist_evidence_complete:
        return "ready_for_review"
    if work_items:
        return "in_progress"
    return "unknown"


def _missing_items(
    readiness: MarketingReadinessSummary,
    *,
    approval_required: bool,
    human_approved: bool,
) -> list[str]:
    missing: list[str] = []
    if not readiness.specialist_evidence_complete:
        missing.append("specialist_evidence")
    if not readiness.review_complete:
        missing.append("review_packet")
    if not readiness.synthesis_complete:
        missing.append("hq_synthesis_packet")
    if approval_required and not human_approved and not readiness.human_approval_ready:
        missing.append("human_approval")
    return missing


def _next_action(status: str, missing: list[str], readiness: MarketingReadinessSummary) -> str:
    if status == "blocked":
        return "Resolve blocked marketing work items."
    if "specialist_evidence" in missing:
        return "Complete specialist mock evidence packets."
    if "review_packet" in missing:
        return "Run marketing reviewer or complete mock review packet."
    if "hq_synthesis_packet" in missing:
        return "Run Clone Banks HQ synthesis or complete mock synthesis packet."
    if readiness.human_approval_ready:
        return "Hall can review the mock HQ synthesis memo. No production action is allowed from mock evidence."
    return "Marketing workflow summary is complete."


def _review_metadata_complete(item: dict[str, Any] | None) -> bool:
    if item is None:
        return False
    metadata = _metadata(item)
    return _item_status(item) in COMPLETE_STATUSES or bool(metadata.get("review_packet_ids"))


def _synthesis_metadata_complete(item: dict[str, Any] | None) -> bool:
    if item is None:
        return False
    metadata = _metadata(item)
    return _item_status(item) in COMPLETE_STATUSES or bool(
        metadata.get("hq_synthesis_packet_ids") or metadata.get("synthesis_packet_ids")
    )


def _human_approved(work_items: list[dict[str, Any]]) -> bool:
    for item in work_items:
        value = _metadata(item).get("human_approval_status") or _metadata(item).get("human_approval")
        if str(value).lower() in {"approved", "completed", "true"}:
            return True
    return False


def _item_for_agent(work_items: list[dict[str, Any]], agent_id: str, *, role: str) -> dict[str, Any] | None:
    matching = [
        item
        for item in work_items
        if item.get("owner_agent") == agent_id and _metadata(item).get("work_item_role") == role
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


def _evidence_ids(item: dict[str, Any]) -> list[str]:
    raw_ids = _metadata(item).get("evidence_packet_ids", [])
    if not isinstance(raw_ids, list):
        return []
    return [str(value) for value in raw_ids if value]


def _review_packet_ids(item: dict[str, Any] | None) -> list[str]:
    if item is None:
        return []
    raw_ids = _metadata(item).get("review_packet_ids", [])
    if not isinstance(raw_ids, list):
        return []
    return [str(value) for value in raw_ids if value]


def _evidence_by_work_item(evidence_packets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for packet in evidence_packets:
        work_item_id = packet.get("work_item_id")
        if work_item_id:
            grouped.setdefault(str(work_item_id), []).append(packet)
    return grouped


def _evidence_count(item: dict[str, Any] | None, evidence_by_work_item: dict[str, list[dict[str, Any]]]) -> int:
    work_item_id = _work_item_id(item)
    return len(evidence_by_work_item.get(work_item_id, [])) if work_item_id else 0


def _evidence_types(item: dict[str, Any] | None, evidence_by_work_item: dict[str, list[dict[str, Any]]]) -> list[str]:
    work_item_id = _work_item_id(item)
    if not work_item_id:
        return []
    types: list[str] = []
    for packet in evidence_by_work_item.get(work_item_id, []):
        artifact_type = _artifact_type(packet)
        if artifact_type:
            types.append(artifact_type)
    return sorted(set(types))


def _artifact_packet_for_item(
    item: dict[str, Any] | None,
    evidence_by_work_item: dict[str, list[dict[str, Any]]],
    artifact_type: str,
) -> dict[str, Any] | None:
    work_item_id = _work_item_id(item)
    if not work_item_id:
        return None
    for packet in evidence_by_work_item.get(work_item_id, []):
        if _artifact_type(packet) == artifact_type:
            return packet
    return None


def _artifact_content(packet: dict[str, Any] | None) -> dict[str, Any]:
    if packet is None:
        return {}
    test_results = packet.get("test_results")
    return test_results if isinstance(test_results, dict) else {}


def _artifact_type(packet: dict[str, Any] | None) -> str | None:
    content = _artifact_content(packet)
    value = content.get("artifact_type") or content.get("evidence_type") or packet.get("type") if packet else None
    return str(value) if value else None


def _artifact_id(packet: dict[str, Any] | None) -> str | None:
    if packet is None:
        return None
    value = packet.get("evidence_id") or packet.get("id")
    return str(value) if value else None


def _artifact_status(item: dict[str, Any] | None, packet: dict[str, Any] | None) -> str:
    if packet is not None:
        return "completed"
    return _item_status(item)


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _item_status(item: dict[str, Any] | None) -> str:
    if item is None:
        return "missing"
    return str(item.get("status") or "unknown")


def _work_item_id(item: dict[str, Any] | None) -> str | None:
    if item is None:
        return None
    value = item.get("work_item_id") or item.get("id")
    return str(value) if value else None


def _string_or_none(value: Any) -> str | None:
    return str(value) if value is not None else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _min_timestamp(items: list[dict[str, Any]], key: str) -> str | None:
    values = sorted(str(item[key]) for item in items if item.get(key))
    return values[0] if values else None


def _max_timestamp(items: list[dict[str, Any]], key: str) -> str | None:
    values = sorted(str(item[key]) for item in items if item.get(key))
    return values[-1] if values else None
