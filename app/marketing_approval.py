from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from app.marketing_approval_contract import MarketingApprovalRecord, MarketingApprovalRequest
from app.marketing_loop import MARKETING_REPOSITORY, REVIEW_AGENT, SPECIALIST_AGENTS, SYNTHESIS_AGENT
from app.marketing_summary import REVIEW_ARTIFACT_TYPE, SYNTHESIS_ARTIFACT_TYPE

HUMAN_APPROVAL_ARTIFACT_TYPE = "human_approval"
APPROVAL_STATE_BY_DECISION = {
    "approve_mock": "approved_mock_only",
    "reject_mock": "rejected_mock_only",
    "request_changes": "changes_requested_mock_only",
}


class MarketingApprovalError(Exception):
    pass


class MarketingApprovalValidationError(MarketingApprovalError):
    pass


class MarketingApprovalAgentBusClient(Protocol):
    async def list_work_items(self, *, repository: str | None = None) -> list[dict[str, Any]]: ...
    async def transition_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def create_evidence_packet(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def get_evidence_packet(self, evidence_id: str) -> dict[str, Any]: ...
    async def attach_evidence_to_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...


async def record_marketing_mock_approval(
    *,
    agent_bus_client: MarketingApprovalAgentBusClient,
    workflow_id: str,
    payload: MarketingApprovalRequest,
) -> MarketingApprovalRecord:
    work_items = await _workflow_work_items(agent_bus_client, workflow_id)
    evidence_packets = await _load_evidence_packets(agent_bus_client, work_items)
    evidence_by_work_item = _evidence_by_work_item(evidence_packets)
    specialist_items = [_item_for_agent(work_items, agent_id, role="specialist_evidence") for agent_id in SPECIALIST_AGENTS]
    review_item = _item_for_agent(work_items, REVIEW_AGENT, role="marketing_review")
    synthesis_item = _item_for_agent(work_items, SYNTHESIS_AGENT, role="hq_synthesis")
    review_artifact = _artifact_packet_for_item(review_item, evidence_by_work_item, REVIEW_ARTIFACT_TYPE)
    synthesis_artifact = _artifact_packet_for_item(synthesis_item, evidence_by_work_item, SYNTHESIS_ARTIFACT_TYPE)

    _validate_approval_prerequisites(
        specialist_items=specialist_items,
        evidence_by_work_item=evidence_by_work_item,
        review_artifact=review_artifact,
        synthesis_item=synthesis_item,
        synthesis_artifact=synthesis_artifact,
    )
    synthesis_artifact_id = _artifact_id(synthesis_artifact)
    if payload.artifact_id and payload.artifact_id != synthesis_artifact_id:
        raise MarketingApprovalValidationError("Approval artifact_id must match the workflow synthesis_memo artifact.")

    existing = _artifact_packet_for_item(synthesis_item, evidence_by_work_item, HUMAN_APPROVAL_ARTIFACT_TYPE)
    if existing is not None:
        return _approval_record_from_packet(workflow_id, existing)

    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    approval_state = APPROVAL_STATE_BY_DECISION[payload.decision]
    content = {
        "artifact_type": HUMAN_APPROVAL_ARTIFACT_TYPE,
        "evidence_type": HUMAN_APPROVAL_ARTIFACT_TYPE,
        "workflow_id": workflow_id,
        "decision": payload.decision,
        "approval_state": approval_state,
        "approved_by": payload.approved_by,
        "notes": payload.notes,
        "approved_artifact_id": synthesis_artifact_id,
        "approved_artifact_type": SYNTHESIS_ARTIFACT_TYPE,
        "mock_mode": True,
        "confidence": "mock_only",
        "live_platform_access": False,
        "no_production_write_performed": True,
        "no_external_platform_action_performed": True,
        "not_for_real_marketing_decisions": True,
        "created_at": created_at,
    }
    packet = await agent_bus_client.create_evidence_packet(
        {
            "work_item_id": _work_item_id(synthesis_item),
            "repository": MARKETING_REPOSITORY,
            "implementation_agent": payload.approved_by,
            "branch": "agent-integration",
            "commit_shas": [],
            "changed_files": [],
            "test_commands": ["marketing-human-approval-mock"],
            "test_results": content,
            "verification_summary": "Human mock approval decision recorded. No production action was performed.",
            "assumptions": ["This is a mock approval record only."],
            "unverified_items": ["Approval does not authorize production marketing action."],
        }
    )
    approval_artifact_id = _artifact_id(packet)
    await agent_bus_client.attach_evidence_to_work_item(
        _work_item_id(synthesis_item),
        {"evidence_id": approval_artifact_id, "actor": payload.approved_by},
    )
    await _transition_if_supported(
        agent_bus_client,
        _work_item_id(synthesis_item),
        {
            "status": "completed",
            "actor": payload.approved_by,
            "metadata": {
                "human_approval_status": approval_state,
                "human_approval_artifact_id": approval_artifact_id,
                "human_approval_decision": payload.decision,
                "no_production_write_performed": True,
            },
        },
    )
    return _approval_record_from_packet(workflow_id, packet)


async def get_marketing_mock_approval(
    *,
    agent_bus_client: MarketingApprovalAgentBusClient,
    workflow_id: str,
) -> MarketingApprovalRecord:
    work_items = await _workflow_work_items(agent_bus_client, workflow_id)
    evidence_packets = await _load_evidence_packets(agent_bus_client, work_items)
    evidence_by_work_item = _evidence_by_work_item(evidence_packets)
    synthesis_item = _item_for_agent(work_items, SYNTHESIS_AGENT, role="hq_synthesis")
    approval_artifact = _artifact_packet_for_item(synthesis_item, evidence_by_work_item, HUMAN_APPROVAL_ARTIFACT_TYPE)
    if approval_artifact is None:
        return MarketingApprovalRecord(
            workflow_id=workflow_id,
            approval_state="not_approved",
            next_action="Hall can review the mock HQ synthesis memo.",
        )
    return _approval_record_from_packet(workflow_id, approval_artifact)


async def _workflow_work_items(client: MarketingApprovalAgentBusClient, workflow_id: str) -> list[dict[str, Any]]:
    work_items = [
        item
        for item in await client.list_work_items(repository=MARKETING_REPOSITORY)
        if _metadata(item).get("workflow_id") == workflow_id
    ]
    if not work_items:
        raise MarketingApprovalValidationError(f"No marketing work items found for workflow_id={workflow_id}.")
    return work_items


async def _load_evidence_packets(
    client: MarketingApprovalAgentBusClient,
    work_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in work_items:
        for evidence_id in _evidence_ids(item):
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            packets.append(await client.get_evidence_packet(evidence_id))
    return packets


def _validate_approval_prerequisites(
    *,
    specialist_items: list[dict[str, Any] | None],
    evidence_by_work_item: dict[str, list[dict[str, Any]]],
    review_artifact: dict[str, Any] | None,
    synthesis_item: dict[str, Any] | None,
    synthesis_artifact: dict[str, Any] | None,
) -> None:
    if not all(item is not None and _evidence_count(item, evidence_by_work_item) > 0 for item in specialist_items):
        raise MarketingApprovalValidationError("Approval requires completed specialist mock evidence.")
    if review_artifact is None:
        raise MarketingApprovalValidationError("Approval requires a completed risk_review artifact.")
    if synthesis_item is None or synthesis_artifact is None:
        raise MarketingApprovalValidationError("Approval requires a completed synthesis_memo artifact.")


def _approval_record_from_packet(workflow_id: str, packet: dict[str, Any]) -> MarketingApprovalRecord:
    content = _artifact_content(packet)
    return MarketingApprovalRecord(
        workflow_id=workflow_id,
        approval_state=str(content.get("approval_state") or "not_approved"),
        approval_artifact_id=_artifact_id(packet),
        approved_by=_string_or_none(content.get("approved_by")),
        decision=content.get("decision"),
        notes=_string_or_none(content.get("notes")),
        approved_artifact_id=_string_or_none(content.get("approved_artifact_id")),
        approved_artifact_type=_string_or_none(content.get("approved_artifact_type")),
        mock_mode=bool(content.get("mock_mode", True)),
        confidence=str(content.get("confidence") or "mock_only"),
        live_platform_access=bool(content.get("live_platform_access", False)),
        no_production_write_performed=bool(content.get("no_production_write_performed", True)),
        no_external_platform_action_performed=bool(content.get("no_external_platform_action_performed", True)),
        not_for_real_marketing_decisions=bool(content.get("not_for_real_marketing_decisions", True)),
        created_at=_string_or_none(content.get("created_at")),
    )


async def _transition_if_supported(client: MarketingApprovalAgentBusClient, work_item_id: str, payload: dict[str, Any]) -> None:
    try:
        await client.transition_work_item(work_item_id, payload)
    except Exception:
        return


def _item_for_agent(work_items: list[dict[str, Any]], agent_id: str, *, role: str) -> dict[str, Any] | None:
    matching = [item for item in work_items if item.get("owner_agent") == agent_id and _metadata(item).get("work_item_role") == role]
    if not matching:
        return None
    return sorted(matching, key=lambda item: str(item.get("created_at") or ""))[0]


def _artifact_packet_for_item(
    item: dict[str, Any] | None,
    evidence_by_work_item: dict[str, list[dict[str, Any]]],
    artifact_type: str,
) -> dict[str, Any] | None:
    work_item_id = _work_item_id_or_none(item)
    if not work_item_id:
        return None
    for packet in evidence_by_work_item.get(work_item_id, []):
        if _artifact_type(packet) == artifact_type:
            return packet
    return None


def _evidence_by_work_item(packets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for packet in packets:
        work_item_id = packet.get("work_item_id")
        if work_item_id:
            grouped.setdefault(str(work_item_id), []).append(packet)
    return grouped


def _evidence_count(item: dict[str, Any] | None, evidence_by_work_item: dict[str, list[dict[str, Any]]]) -> int:
    work_item_id = _work_item_id_or_none(item)
    return len(evidence_by_work_item.get(work_item_id, [])) if work_item_id else 0


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


def _artifact_id(packet: dict[str, Any] | None) -> str | None:
    if packet is None:
        return None
    value = packet.get("evidence_id") or packet.get("id")
    return str(value) if value else None


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _work_item_id(item: dict[str, Any]) -> str:
    value = item.get("work_item_id") or item.get("id")
    if not value:
        raise MarketingApprovalValidationError("Agent Bus work item did not include work_item_id.")
    return str(value)


def _work_item_id_or_none(item: dict[str, Any] | None) -> str | None:
    return _work_item_id(item) if item is not None else None


def _string_or_none(value: Any) -> str | None:
    return str(value) if value is not None else None
