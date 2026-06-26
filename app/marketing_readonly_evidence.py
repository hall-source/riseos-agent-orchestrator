from __future__ import annotations

from typing import Any, Protocol

from app.marketing_loop import MARKETING_REPOSITORY, MARKETING_WORKFLOW_TYPE, REVIEW_AGENT
from app.marketing_readonly_evidence_contract import (
    AttachReadOnlyFixtureEvidenceRequest,
    AttachReadOnlyFixtureEvidenceResponse,
)

HALL_DATA_AGENT = "hall-data-intelligence"
ANALYTICS_EVIDENCE_TYPE = "analytics_snapshot"
READ_ONLY_FIXTURE_SOURCE_MODE = "read_only_fixture"


class MarketingReadOnlyEvidenceError(Exception):
    pass


class MarketingReadOnlyEvidenceValidationError(MarketingReadOnlyEvidenceError):
    pass


class MarketingReadOnlyEvidenceAgentBusClient(Protocol):
    async def list_work_items(self, *, repository: str | None = None) -> list[dict[str, Any]]: ...
    async def create_evidence_packet(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def attach_evidence_to_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...


async def attach_read_only_fixture_evidence(
    *,
    agent_bus_client: MarketingReadOnlyEvidenceAgentBusClient,
    payload: AttachReadOnlyFixtureEvidenceRequest,
) -> AttachReadOnlyFixtureEvidenceResponse:
    work_item = await _find_work_item(agent_bus_client, payload.work_item_id)
    metadata = _metadata(work_item)
    _validate_work_item(work_item, requested_workflow_id=payload.workflow_id)
    workflow_id = str(metadata.get("workflow_id") or payload.workflow_id or "") or None
    fixture = payload.fixture.dict()
    derived_metrics = _derived_metrics(fixture)
    evidence_payload = {
        "work_item_id": payload.work_item_id,
        "repository": MARKETING_REPOSITORY,
        "implementation_agent": HALL_DATA_AGENT,
        "branch": "agent-integration",
        "commit_shas": [],
        "changed_files": [],
        "test_commands": ["marketing-read-only-fixture-attach"],
        "test_results": {
            "evidence_type": ANALYTICS_EVIDENCE_TYPE,
            "artifact_type": ANALYTICS_EVIDENCE_TYPE,
            "produced_by": HALL_DATA_AGENT,
            "workflow_id": workflow_id,
            "workflow_type": MARKETING_WORKFLOW_TYPE,
            "source_mode": READ_ONLY_FIXTURE_SOURCE_MODE,
            "source_label": "weekly_marketing_snapshot_fixture",
            "mode": "mock_only",
            "fixture": fixture,
            "derived_metrics": derived_metrics,
            "confidence": "fixture_only",
            "live_platform_access": False,
            "write_access": False,
            "not_for_real_marketing_decisions": True,
            "approval_required": False,
            "mock_mode": False,
            "review_agent": REVIEW_AGENT,
        },
        "verification_summary": "Read-only fixture analytics snapshot attached. No live platform access or writes occurred.",
        "assumptions": ["Fixture payload was provided by an authenticated orchestrator admin."],
        "unverified_items": ["Fixture data is not verified against live marketing platforms."],
    }
    evidence = await agent_bus_client.create_evidence_packet(evidence_payload)
    evidence_packet_id = _response_id(evidence, "evidence_id")
    await agent_bus_client.attach_evidence_to_work_item(
        payload.work_item_id,
        {"evidence_id": evidence_packet_id, "actor": HALL_DATA_AGENT},
    )
    return AttachReadOnlyFixtureEvidenceResponse(
        workflow_id=workflow_id,
        work_item_id=payload.work_item_id,
        evidence_packet_id=evidence_packet_id,
        derived_metrics=derived_metrics,
    )


async def _find_work_item(client: MarketingReadOnlyEvidenceAgentBusClient, work_item_id: str) -> dict[str, Any]:
    for item in await client.list_work_items(repository=MARKETING_REPOSITORY):
        if str(item.get("work_item_id") or item.get("id") or "") == work_item_id:
            return item
    raise MarketingReadOnlyEvidenceValidationError(f"Marketing work item not found: {work_item_id}")


def _validate_work_item(item: dict[str, Any], *, requested_workflow_id: str | None) -> None:
    metadata = _metadata(item)
    if item.get("owner_agent") != HALL_DATA_AGENT:
        raise MarketingReadOnlyEvidenceValidationError("Read-only fixture evidence is only supported for hall-data-intelligence.")
    if metadata.get("workflow_type") != MARKETING_WORKFLOW_TYPE:
        raise MarketingReadOnlyEvidenceValidationError("Unsupported marketing workflow type for read-only fixture evidence.")
    if metadata.get("work_item_role") not in {"specialist", "specialist_evidence"}:
        raise MarketingReadOnlyEvidenceValidationError("Read-only fixture evidence can only attach to specialist work items.")
    if requested_workflow_id and metadata.get("workflow_id") != requested_workflow_id:
        raise MarketingReadOnlyEvidenceValidationError("Requested workflow_id does not match the work item workflow_id.")
    if metadata.get("live_platform_access") is not False:
        raise MarketingReadOnlyEvidenceValidationError("Read-only fixture evidence requires live_platform_access=false on the work item.")


def _derived_metrics(fixture: dict[str, Any]) -> dict[str, float]:
    sessions = float(fixture["website_sessions"])
    leads = float(fixture["leads"])
    qualified_leads = float(fixture["qualified_leads"])
    deals_created = float(fixture["deals_created"])
    return {
        "lead_conversion_rate": _rate(leads, sessions),
        "qualified_lead_rate": _rate(qualified_leads, leads),
        "deal_created_rate": _rate(deals_created, leads),
        "deal_created_per_session_rate": _rate(deals_created, sessions),
    }


def _rate(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _response_id(response: dict[str, Any], key: str) -> str:
    value = response.get(key) or response.get("id")
    if not value:
        raise MarketingReadOnlyEvidenceValidationError(f"Agent Bus response did not include {key}.")
    return str(value)
