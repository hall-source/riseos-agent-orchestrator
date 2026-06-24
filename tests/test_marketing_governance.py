from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.clients.agent_bus import AgentBusAPIError
from app.config import Settings, get_settings
from app.main import app
from app.marketing_governance import MarketingGovernanceValidationError, run_marketing_governance_once
from app.marketing_loop import MARKETING_REPOSITORY, MARKETING_WORKFLOW_TYPE, REVIEW_AGENT, SPECIALIST_AGENTS, SYNTHESIS_AGENT


class FakeMarketingGovernanceAgentBusClient:
    def __init__(self, work_items: list[dict[str, object]] | None = None) -> None:
        self.work_items: list[dict[str, object]] = work_items or []
        self.evidence_packets: dict[str, dict[str, object]] = {}
        self.created_work_items: list[dict[str, object]] = []
        self.created_evidence_packets: list[dict[str, object]] = []
        self.attached_evidence: list[tuple[str, dict[str, object]]] = []
        self.transitions: list[tuple[str, dict[str, object]]] = []
        self.completed: list[tuple[str, dict[str, object]]] = []
        self.external_calls: list[str] = []

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

    def add_specialist_evidence(self, item: dict[str, object], *, evidence_type: str = "analytics_snapshot") -> str:
        evidence_id = f"ev-{uuid4()}"
        packet = {
            "evidence_id": evidence_id,
            "work_item_id": item["work_item_id"],
            "repository": MARKETING_REPOSITORY,
            "implementation_agent": item["owner_agent"],
            "test_results": {
                "evidence_type": evidence_type,
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


def specialist_work_item(agent_id: str, *, workflow_id: str = "marketing-wf-governance") -> dict[str, object]:
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


def workflow_with_specialist_evidence() -> tuple[FakeMarketingGovernanceAgentBusClient, str, list[str]]:
    workflow_id = "marketing-wf-governance"
    work_items = [specialist_work_item(agent_id, workflow_id=workflow_id) for agent_id in SPECIALIST_AGENTS]
    fake = FakeMarketingGovernanceAgentBusClient(work_items)
    evidence_ids = [fake.add_specialist_evidence(item) for item in work_items]
    return fake, workflow_id, evidence_ids


def client_with_fake_agent_bus(
    fake_client: FakeMarketingGovernanceAgentBusClient,
    *,
    enable_governance: bool,
) -> TestClient:
    get_settings.cache_clear()
    app.dependency_overrides[get_settings] = lambda: Settings(
        github_webhook_secret="test-secret",
        orchestrator_admin_token="admin-token",
        agent_bus_base_url="http://127.0.0.1:8050",
        enable_marketing_governance_mock=enable_governance,
    )
    app.state.agent_bus_client = fake_client
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()
    if hasattr(app.state, "agent_bus_client"):
        delattr(app.state, "agent_bus_client")
    get_settings.cache_clear()


def generated_artifacts(fake: FakeMarketingGovernanceAgentBusClient) -> list[dict[str, object]]:
    return fake.created_evidence_packets


def artifact_by_type(fake: FakeMarketingGovernanceAgentBusClient, artifact_type: str) -> dict[str, object]:
    for packet in generated_artifacts(fake):
        results = packet["test_results"]
        if isinstance(results, dict) and results.get("artifact_type") == artifact_type:
            return packet
    raise AssertionError(f"Missing artifact type {artifact_type}")


def test_governance_endpoint_requires_admin_auth() -> None:
    fake, workflow_id, _ = workflow_with_specialist_evidence()
    client = client_with_fake_agent_bus(fake, enable_governance=True)

    response = client.post("/api/v1/marketing/governance/mock/run-once", json={"workflow_id": workflow_id})

    assert response.status_code == 401


def test_governance_endpoint_respects_enable_marketing_governance_mock_flag() -> None:
    fake, workflow_id, _ = workflow_with_specialist_evidence()
    client = client_with_fake_agent_bus(fake, enable_governance=False)

    response = client.post(
        "/api/v1/marketing/governance/mock/run-once",
        headers={"Authorization": "Bearer admin-token"},
        json={"workflow_id": workflow_id, "run_reviewer": True, "run_hq_synthesis": True},
    )

    assert response.status_code == 403
    assert "ENABLE_MARKETING_GOVERNANCE_MOCK" in response.json()["detail"]
    assert generated_artifacts(fake) == []


def test_governance_runner_refuses_to_run_when_specialist_evidence_is_missing() -> None:
    workflow_id = "marketing-wf-governance"
    fake = FakeMarketingGovernanceAgentBusClient(
        [specialist_work_item(agent_id, workflow_id=workflow_id) for agent_id in SPECIALIST_AGENTS]
    )

    with pytest.raises(MarketingGovernanceValidationError, match="Run the specialist worker before governance"):
        asyncio.run(run_marketing_governance_once(agent_bus_client=fake, workflow_id=workflow_id))

    assert generated_artifacts(fake) == []


def test_governance_runner_creates_risk_review() -> None:
    fake, workflow_id, _ = workflow_with_specialist_evidence()

    response = asyncio.run(run_marketing_governance_once(agent_bus_client=fake, workflow_id=workflow_id))

    assert response.reviewer_result is not None
    assert response.reviewer_result.status == "completed"
    assert response.reviewer_result.artifact_type == "risk_review"
    packet = artifact_by_type(fake, "risk_review")
    assert packet["implementation_agent"] == REVIEW_AGENT


def test_governance_runner_creates_synthesis_memo() -> None:
    fake, workflow_id, _ = workflow_with_specialist_evidence()

    response = asyncio.run(run_marketing_governance_once(agent_bus_client=fake, workflow_id=workflow_id))

    assert response.hq_result is not None
    assert response.hq_result.status == "completed"
    assert response.hq_result.artifact_type == "synthesis_memo"
    packet = artifact_by_type(fake, "synthesis_memo")
    assert packet["implementation_agent"] == SYNTHESIS_AGENT


def test_risk_review_references_specialist_evidence_packet_ids() -> None:
    fake, workflow_id, evidence_ids = workflow_with_specialist_evidence()

    asyncio.run(run_marketing_governance_once(agent_bus_client=fake, workflow_id=workflow_id))

    packet = artifact_by_type(fake, "risk_review")
    results = packet["test_results"]
    assert isinstance(results, dict)
    assert set(results["referenced_evidence_packet_ids"]) == set(evidence_ids)


def test_synthesis_memo_references_specialist_evidence_and_review_artifact() -> None:
    fake, workflow_id, evidence_ids = workflow_with_specialist_evidence()

    response = asyncio.run(run_marketing_governance_once(agent_bus_client=fake, workflow_id=workflow_id))

    packet = artifact_by_type(fake, "synthesis_memo")
    results = packet["test_results"]
    assert isinstance(results, dict)
    assert set(results["referenced_evidence_packet_ids"]) == set(evidence_ids)
    assert results["referenced_review_artifact_id"] == response.reviewer_result.artifact_id


def test_summary_endpoint_reports_review_and_synthesis_complete_after_governance_run() -> None:
    fake, workflow_id, _ = workflow_with_specialist_evidence()
    client = client_with_fake_agent_bus(fake, enable_governance=True)

    governance_response = client.post(
        "/api/v1/marketing/governance/mock/run-once",
        headers={"Authorization": "Bearer admin-token"},
        json={"workflow_id": workflow_id, "run_reviewer": True, "run_hq_synthesis": True},
    )
    summary_response = client.get(
        f"/api/v1/marketing/workflows/{workflow_id}/summary",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert governance_response.status_code == 200
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["review"]["ready"] is True
    assert summary["synthesis"]["ready"] is True
    assert summary["readiness"]["specialist_evidence_complete"] is True
    assert summary["readiness"]["review_complete"] is True
    assert summary["readiness"]["synthesis_complete"] is True
    assert summary["readiness"]["human_approval_ready"] is True
    assert summary["next_action"] == "Hall can review the mock HQ synthesis memo. No production action is allowed from mock evidence."


def test_generated_governance_artifacts_include_mock_only_safeguards() -> None:
    fake, workflow_id, _ = workflow_with_specialist_evidence()

    asyncio.run(run_marketing_governance_once(agent_bus_client=fake, workflow_id=workflow_id))

    for artifact_type in {"risk_review", "synthesis_memo"}:
        packet = artifact_by_type(fake, artifact_type)
        results = packet["test_results"]
        assert isinstance(results, dict)
        assert results["mock_mode"] is True
        assert results["confidence"] == "mock_only"
        assert results["live_platform_access"] is False
        assert results["not_for_real_marketing_decisions"] is True
        assert results["human_approval_required"] is True


def test_governance_runner_does_not_call_live_integrations() -> None:
    fake, workflow_id, _ = workflow_with_specialist_evidence()

    response = asyncio.run(run_marketing_governance_once(agent_bus_client=fake, workflow_id=workflow_id))

    assert response.mock_mode is True
    assert response.live_platform_access is False
    assert fake.external_calls == []
    for packet in generated_artifacts(fake):
        results = packet["test_results"]
        assert isinstance(results, dict)
        assert results["live_platform_access"] is False
