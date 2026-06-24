from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from app.clients.agent_bus import AgentBusAPIError
from app.config import Settings, get_settings
from app.main import app
from app.marketing_approval import MarketingApprovalValidationError, record_marketing_mock_approval
from app.marketing_approval_contract import MarketingApprovalRequest
from app.marketing_governance import run_marketing_governance_once
from app.marketing_loop import MARKETING_REPOSITORY, MARKETING_WORKFLOW_TYPE, REVIEW_AGENT, SPECIALIST_AGENTS


class FakeMarketingApprovalAgentBusClient:
    def __init__(self, work_items: list[dict[str, object]] | None = None) -> None:
        self.work_items: list[dict[str, object]] = work_items or []
        self.evidence_packets: dict[str, dict[str, object]] = {}
        self.created_evidence_packets: list[dict[str, object]] = []
        self.created_work_items: list[dict[str, object]] = []
        self.attached_evidence: list[tuple[str, dict[str, object]]] = []
        self.transitions: list[tuple[str, dict[str, object]]] = []
        self.completed: list[tuple[str, dict[str, object]]] = []
        self.external_writes: list[str] = []

    async def list_work_items(self, *, repository: str | None = None) -> list[dict[str, object]]:
        if repository is None:
            return self.work_items
        return [item for item in self.work_items if item.get("repository") == repository]

    async def create_work_item(self, payload: dict[str, object]) -> dict[str, object]:
        item = {
            **payload,
            "work_item_id": f"wi-{uuid4()}",
            "status": "queued",
            "created_at": "2026-06-24T18:00:00Z",
            "updated_at": "2026-06-24T18:00:00Z",
        }
        self.work_items.append(item)
        self.created_work_items.append(item)
        return item

    async def transition_work_item(self, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.transitions.append((work_item_id, payload))
        item = self._item(work_item_id)
        item["status"] = payload["status"]
        metadata = item.setdefault("metadata", {})
        if isinstance(metadata, dict) and isinstance(payload.get("metadata"), dict):
            metadata.update(payload["metadata"])
        return item

    async def complete_work_item(self, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.completed.append((work_item_id, payload))
        item = self._item(work_item_id)
        item["status"] = "completed"
        metadata = item.setdefault("metadata", {})
        if isinstance(metadata, dict) and isinstance(payload.get("metadata"), dict):
            metadata.update(payload["metadata"])
        return item

    async def create_evidence_packet(self, payload: dict[str, object]) -> dict[str, object]:
        evidence_id = f"ev-{uuid4()}"
        packet = {**payload, "evidence_id": evidence_id}
        self.evidence_packets[evidence_id] = packet
        self.created_evidence_packets.append(packet)
        return packet

    async def get_evidence_packet(self, evidence_id: str) -> dict[str, object]:
        try:
            return self.evidence_packets[evidence_id]
        except KeyError as exc:
            raise AgentBusAPIError("GET", f"/evidence-packets/{evidence_id}", 404, "Evidence packet not found") from exc

    async def attach_evidence_to_work_item(self, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.attached_evidence.append((work_item_id, payload))
        item = self._item(work_item_id)
        metadata = item.setdefault("metadata", {})
        if isinstance(metadata, dict):
            evidence_ids = metadata.setdefault("evidence_packet_ids", [])
            if isinstance(evidence_ids, list):
                evidence_ids.append(payload["evidence_id"])
        return item

    def add_specialist_evidence(self, item: dict[str, object]) -> str:
        evidence_id = f"ev-{uuid4()}"
        packet = {
            "evidence_id": evidence_id,
            "work_item_id": item["work_item_id"],
            "repository": MARKETING_REPOSITORY,
            "implementation_agent": item["owner_agent"],
            "test_results": {
                "evidence_type": "analytics_snapshot",
                "confidence": "mock_only",
                "mode": "mock_only",
                "mock_mode": True,
                "live_platform_access": False,
                "not_for_real_marketing_decisions": True,
                "approval_required": False,
            },
            "verification_summary": "Mock specialist evidence.",
        }
        self.evidence_packets[evidence_id] = packet
        metadata = item.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata.setdefault("evidence_packet_ids", []).append(evidence_id)
        return evidence_id

    def _item(self, work_item_id: str) -> dict[str, object]:
        for item in self.work_items:
            if item.get("work_item_id") == work_item_id:
                return item
        raise AgentBusAPIError("GET", f"/work-items/{work_item_id}", 404, "Work item not found")


def specialist_work_item(agent_id: str, *, workflow_id: str = "marketing-wf-approval") -> dict[str, object]:
    return {
        "work_item_id": f"wi-{uuid4()}",
        "title": f"Mock specialist: {agent_id}",
        "repository": MARKETING_REPOSITORY,
        "status": "completed",
        "owner_agent": agent_id,
        "review_agent": REVIEW_AGENT,
        "created_at": "2026-06-24T18:00:00Z",
        "updated_at": "2026-06-24T18:00:00Z",
        "metadata": {
            "domain": "marketing",
            "brand": "rise",
            "business_unit": "RISE Commercial District",
            "workflow_id": workflow_id,
            "workflow_type": MARKETING_WORKFLOW_TYPE,
            "work_item_role": "specialist_evidence",
            "requested_by": "Hall",
            "human_owner": "Hall",
            "mock_mode": True,
            "mvp_mode": "mock_only",
            "live_platform_access": False,
            "approval_required": True,
        },
    }


def workflow_with_specialist_evidence() -> tuple[FakeMarketingApprovalAgentBusClient, str]:
    workflow_id = f"marketing-wf-approval-{uuid4()}"
    items = [specialist_work_item(agent_id, workflow_id=workflow_id) for agent_id in SPECIALIST_AGENTS]
    fake = FakeMarketingApprovalAgentBusClient(items)
    for item in items:
        fake.add_specialist_evidence(item)
    return fake, workflow_id


def governed_workflow() -> tuple[FakeMarketingApprovalAgentBusClient, str]:
    fake, workflow_id = workflow_with_specialist_evidence()
    asyncio.run(run_marketing_governance_once(agent_bus_client=fake, workflow_id=workflow_id))
    return fake, workflow_id


def client_with_fake_agent_bus(fake: FakeMarketingApprovalAgentBusClient, *, enable_approval: bool) -> TestClient:
    get_settings.cache_clear()
    app.dependency_overrides[get_settings] = lambda: Settings(
        github_webhook_secret="test-secret",
        orchestrator_admin_token="admin-token",
        agent_bus_base_url="http://127.0.0.1:8050",
        enable_marketing_approval_mock=enable_approval,
    )
    app.state.agent_bus_client = fake
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()
    if hasattr(app.state, "agent_bus_client"):
        delattr(app.state, "agent_bus_client")
    get_settings.cache_clear()


def artifact_by_type(fake: FakeMarketingApprovalAgentBusClient, artifact_type: str) -> dict[str, object]:
    for packet in fake.created_evidence_packets:
        results = packet["test_results"]
        if isinstance(results, dict) and results.get("artifact_type") == artifact_type:
            return packet
    raise AssertionError(f"Missing artifact type {artifact_type}")


def approval_payload(decision: str = "approve_mock") -> dict[str, object]:
    return {
        "decision": decision,
        "approved_by": "Hall",
        "notes": "Mock synthesis reviewed. Safe to proceed to the next development step.",
    }


def test_approval_post_requires_admin_auth() -> None:
    fake, workflow_id = governed_workflow()
    client = client_with_fake_agent_bus(fake, enable_approval=True)

    response = client.post(f"/api/v1/marketing/workflows/{workflow_id}/approval", json=approval_payload())

    assert response.status_code == 401


def test_approval_post_respects_enable_marketing_approval_mock_flag() -> None:
    fake, workflow_id = governed_workflow()
    client = client_with_fake_agent_bus(fake, enable_approval=False)

    response = client.post(
        f"/api/v1/marketing/workflows/{workflow_id}/approval",
        headers={"Authorization": "Bearer admin-token"},
        json=approval_payload(),
    )

    assert response.status_code == 403
    assert "ENABLE_MARKETING_APPROVAL_MOCK" in response.json()["detail"]


def test_approval_refuses_when_synthesis_memo_is_missing() -> None:
    fake, workflow_id = workflow_with_specialist_evidence()

    try:
        asyncio.run(
            record_marketing_mock_approval(
                agent_bus_client=fake,
                workflow_id=workflow_id,
                payload=MarketingApprovalRequest(**approval_payload()),
            )
        )
    except MarketingApprovalValidationError as exc:
        assert "risk_review" in str(exc) or "synthesis_memo" in str(exc)
    else:
        raise AssertionError("Approval should fail without governance artifacts")


def test_approval_refuses_when_review_artifact_is_missing() -> None:
    fake, workflow_id = workflow_with_specialist_evidence()
    hq_item = asyncio.run(fake.create_work_item({
        "title": "Mock HQ synthesis",
        "repository": MARKETING_REPOSITORY,
        "owner_agent": "clone-banks-hq",
        "review_agent": REVIEW_AGENT,
        "metadata": {
            "workflow_id": workflow_id,
            "workflow_type": MARKETING_WORKFLOW_TYPE,
            "work_item_role": "hq_synthesis",
        },
    }))
    synthesis = asyncio.run(fake.create_evidence_packet({
        "work_item_id": hq_item["work_item_id"],
        "repository": MARKETING_REPOSITORY,
        "implementation_agent": "clone-banks-hq",
        "test_results": {"artifact_type": "synthesis_memo", "confidence": "mock_only", "live_platform_access": False},
    }))
    asyncio.run(fake.attach_evidence_to_work_item(str(hq_item["work_item_id"]), {"evidence_id": synthesis["evidence_id"], "actor": "clone-banks-hq"}))

    try:
        asyncio.run(
            record_marketing_mock_approval(
                agent_bus_client=fake,
                workflow_id=workflow_id,
                payload=MarketingApprovalRequest(**approval_payload()),
            )
        )
    except MarketingApprovalValidationError as exc:
        assert "risk_review" in str(exc)
    else:
        raise AssertionError("Approval should fail without risk_review")


def test_approval_accepts_approve_mock() -> None:
    fake, workflow_id = governed_workflow()

    record = asyncio.run(record_marketing_mock_approval(
        agent_bus_client=fake,
        workflow_id=workflow_id,
        payload=MarketingApprovalRequest(**approval_payload("approve_mock")),
    ))

    assert record.approval_state == "approved_mock_only"
    assert record.decision == "approve_mock"


def test_approval_accepts_reject_mock() -> None:
    fake, workflow_id = governed_workflow()

    record = asyncio.run(record_marketing_mock_approval(
        agent_bus_client=fake,
        workflow_id=workflow_id,
        payload=MarketingApprovalRequest(**approval_payload("reject_mock")),
    ))

    assert record.approval_state == "rejected_mock_only"
    assert record.decision == "reject_mock"


def test_approval_accepts_request_changes() -> None:
    fake, workflow_id = governed_workflow()

    record = asyncio.run(record_marketing_mock_approval(
        agent_bus_client=fake,
        workflow_id=workflow_id,
        payload=MarketingApprovalRequest(**approval_payload("request_changes")),
    ))

    assert record.approval_state == "changes_requested_mock_only"
    assert record.decision == "request_changes"


def test_approval_creates_human_approval_artifact() -> None:
    fake, workflow_id = governed_workflow()

    record = asyncio.run(record_marketing_mock_approval(
        agent_bus_client=fake,
        workflow_id=workflow_id,
        payload=MarketingApprovalRequest(**approval_payload()),
    ))

    packet = artifact_by_type(fake, "human_approval")
    assert packet["evidence_id"] == record.approval_artifact_id
    assert fake.attached_evidence[-1][1]["evidence_id"] == packet["evidence_id"]


def test_get_approval_returns_no_approval_when_none_exists() -> None:
    fake, workflow_id = governed_workflow()
    client = client_with_fake_agent_bus(fake, enable_approval=True)

    response = client.get(
        f"/api/v1/marketing/workflows/{workflow_id}/approval",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    assert response.json()["approval_state"] == "not_approved"
    assert response.json()["next_action"] == "Hall can review the mock HQ synthesis memo."


def test_get_approval_returns_approval_after_decision() -> None:
    fake, workflow_id = governed_workflow()
    client = client_with_fake_agent_bus(fake, enable_approval=True)

    post_response = client.post(
        f"/api/v1/marketing/workflows/{workflow_id}/approval",
        headers={"Authorization": "Bearer admin-token"},
        json=approval_payload(),
    )
    get_response = client.get(
        f"/api/v1/marketing/workflows/{workflow_id}/approval",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert post_response.status_code == 200
    assert get_response.status_code == 200
    assert get_response.json()["approval_state"] == "approved_mock_only"
    assert get_response.json()["approved_by"] == "Hall"


def test_summary_endpoint_includes_approval_state() -> None:
    fake, workflow_id = governed_workflow()
    client = client_with_fake_agent_bus(fake, enable_approval=True)

    approval_response = client.post(
        f"/api/v1/marketing/workflows/{workflow_id}/approval",
        headers={"Authorization": "Bearer admin-token"},
        json=approval_payload(),
    )
    summary_response = client.get(
        f"/api/v1/marketing/workflows/{workflow_id}/summary",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert approval_response.status_code == 200
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["human_approval"]["state"] == "approved_mock_only"
    assert summary["human_approval"]["decision"] == "approve_mock"
    assert summary["human_approval"]["no_production_write_performed"] is True
    assert summary["readiness"]["human_approval_ready"] is True
    assert summary["readiness"]["human_approval_complete"] is True
    assert summary["next_action"] == "Mock workflow approved. No production action was performed. Next development step can begin."


def test_approval_does_not_call_external_write_methods() -> None:
    fake, workflow_id = governed_workflow()

    asyncio.run(record_marketing_mock_approval(
        agent_bus_client=fake,
        workflow_id=workflow_id,
        payload=MarketingApprovalRequest(**approval_payload()),
    ))

    assert fake.external_writes == []


def test_approval_artifact_includes_mock_only_and_no_write_safeguards() -> None:
    fake, workflow_id = governed_workflow()

    asyncio.run(record_marketing_mock_approval(
        agent_bus_client=fake,
        workflow_id=workflow_id,
        payload=MarketingApprovalRequest(**approval_payload()),
    ))

    packet = artifact_by_type(fake, "human_approval")
    results = packet["test_results"]
    assert isinstance(results, dict)
    assert results["mock_mode"] is True
    assert results["confidence"] == "mock_only"
    assert results["live_platform_access"] is False
    assert results["no_production_write_performed"] is True
    assert results["no_external_platform_action_performed"] is True
    assert results["not_for_real_marketing_decisions"] is True
