from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.clients.agent_bus import AgentBusAPIError
from app.config import get_settings
from app.main import app
from app.marketing_agent_registry import MARKETING_AGENT_REGISTRY
from app.marketing_loop import MARKETING_REPOSITORY, MARKETING_WORKFLOW_TYPE, MOCK_EVIDENCE_BY_AGENT
from app.marketing_worker import MarketingWorkerValidationError, process_marketing_specialist_work_item, run_marketing_worker_once


class FakeMarketingWorkerAgentBusClient:
    def __init__(self, work_items: list[dict[str, object]] | None = None) -> None:
        self.work_items: list[dict[str, object]] = work_items or []
        self.evidence_packets: list[dict[str, object]] = []
        self.claimed: list[tuple[str, dict[str, object]]] = []
        self.transitions: list[tuple[str, dict[str, object]]] = []
        self.completed: list[tuple[str, dict[str, object]]] = []
        self.attached_evidence: list[tuple[str, dict[str, object]]] = []

    async def list_work_items(self, *, repository: str | None = None) -> list[dict[str, object]]:
        if repository is None:
            return self.work_items
        return [item for item in self.work_items if item.get("repository") == repository]

    async def claim_work_item(self, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.claimed.append((work_item_id, payload))
        item = self._item(work_item_id)
        item["status"] = "claimed"
        item["owner_agent"] = payload["agent_id"]
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
        evidence_id = str(uuid4())
        packet = {**payload, "evidence_id": evidence_id}
        self.evidence_packets.append(packet)
        return packet

    async def attach_evidence_to_work_item(self, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.attached_evidence.append((work_item_id, payload))
        item = self._item(work_item_id)
        metadata = item.setdefault("metadata", {})
        if isinstance(metadata, dict):
            evidence_ids = metadata.setdefault("evidence_packet_ids", [])
            if isinstance(evidence_ids, list):
                evidence_ids.append(payload["evidence_id"])
        return item

    def _item(self, work_item_id: str) -> dict[str, object]:
        for item in self.work_items:
            if item.get("work_item_id") == work_item_id:
                return item
        raise AgentBusAPIError("GET", f"/work-items/{work_item_id}", 404, "Work item not found")


def marketing_work_item(
    *,
    agent_id: str = "hall-ppc-intelligence",
    workflow_id: str = "marketing-wf-test",
    status: str = "queued",
    domain: str = "marketing",
    work_item_role: str = "specialist",
    mock_mode: bool = True,
    live_platform_access: bool = False,
    repository: str = MARKETING_REPOSITORY,
) -> dict[str, object]:
    return {
        "work_item_id": str(uuid4()),
        "title": f"Mock worker item: {agent_id}",
        "repository": repository,
        "status": status,
        "owner_agent": agent_id,
        "review_agent": "hall-marketing-reviewer",
        "metadata": {
            "domain": domain,
            "workflow_type": MARKETING_WORKFLOW_TYPE,
            "work_item_role": work_item_role,
            "workflow_id": workflow_id,
            "mock_mode": mock_mode,
            "live_platform_access": live_platform_access,
        },
    }


def client_with_fake_agent_bus(
    fake_client: FakeMarketingWorkerAgentBusClient,
    *,
    enable_worker: bool,
) -> TestClient:
    get_settings.cache_clear()
    app.dependency_overrides[get_settings] = lambda: get_settings().__class__(
        github_webhook_secret="test-secret",
        orchestrator_admin_token="admin-token",
        agent_bus_base_url="http://127.0.0.1:8050",
        enable_marketing_worker_mock=enable_worker,
    )
    app.state.agent_bus_client = fake_client
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()
    if hasattr(app.state, "agent_bus_client"):
        delattr(app.state, "agent_bus_client")
    get_settings.cache_clear()


def test_worker_registry_contains_required_marketing_agents() -> None:
    expected_agents = {
        "clone-banks-hq",
        "hall-data-intelligence",
        "hall-ppc-intelligence",
        "hall-seo-intelligence",
        "hall-creative-strategist",
        "hall-marketing-reviewer",
    }

    assert expected_agents <= set(MARKETING_AGENT_REGISTRY)
    for agent_id in expected_agents:
        entry = MARKETING_AGENT_REGISTRY[agent_id]
        assert entry.agent_id == agent_id
        assert entry.display_name
        assert entry.agent_type
        assert entry.capabilities
        assert entry.default_work_item_roles
        assert entry.live_integrations_enabled is False


def test_worker_can_process_one_eligible_mock_specialist_item() -> None:
    item = marketing_work_item(agent_id="hall-ppc-intelligence")
    fake = FakeMarketingWorkerAgentBusClient([item])

    response = asyncio.run(run_marketing_worker_once(agent_bus_client=fake, workflow_id="marketing-wf-test", max_items=1))

    assert response.processed == 1
    result = response.results[0]
    assert result.workflow_id == "marketing-wf-test"
    assert result.agent_id == "hall-ppc-intelligence"
    assert result.work_item_id == item["work_item_id"]
    assert result.status == "completed"
    assert result.evidence_packet_id
    assert result.mock_mode is True
    assert result.live_platform_access is False
    assert result.next_action == "ready_for_review"
    assert fake.claimed == [(str(item["work_item_id"]), {"agent_id": "hall-ppc-intelligence"})]
    assert fake.transitions[0][1]["status"] == "in_progress"
    assert fake.completed[0][0] == item["work_item_id"]


def test_worker_refuses_unknown_agent() -> None:
    item = marketing_work_item(agent_id="unknown-marketing-agent")
    fake = FakeMarketingWorkerAgentBusClient([item])

    with pytest.raises(MarketingWorkerValidationError):
        asyncio.run(process_marketing_specialist_work_item(item, agent_bus_client=fake))


def test_worker_refuses_unsupported_evidence_type() -> None:
    item = marketing_work_item(agent_id="hall-ppc-intelligence")
    fake = FakeMarketingWorkerAgentBusClient([item])
    original = MOCK_EVIDENCE_BY_AGENT["hall-ppc-intelligence"]
    MOCK_EVIDENCE_BY_AGENT["hall-ppc-intelligence"] = {**original, "evidence_type": "unsupported_snapshot"}
    try:
        with pytest.raises(MarketingWorkerValidationError):
            asyncio.run(process_marketing_specialist_work_item(item, agent_bus_client=fake))
    finally:
        MOCK_EVIDENCE_BY_AGENT["hall-ppc-intelligence"] = original


def test_worker_does_not_process_non_marketing_work() -> None:
    item = marketing_work_item(domain="engineering")
    fake = FakeMarketingWorkerAgentBusClient([item])

    response = asyncio.run(run_marketing_worker_once(agent_bus_client=fake, max_items=4))

    assert response.processed == 0
    assert response.results == []
    assert fake.evidence_packets == []


def test_worker_does_not_process_live_mode_work_when_live_integrations_are_disabled() -> None:
    item = marketing_work_item(mock_mode=False, live_platform_access=True)
    fake = FakeMarketingWorkerAgentBusClient([item])

    response = asyncio.run(run_marketing_worker_once(agent_bus_client=fake, max_items=4))

    assert response.processed == 0
    assert response.results == []
    assert fake.evidence_packets == []


def test_worker_attaches_mock_only_evidence_with_no_live_platform_access() -> None:
    item = marketing_work_item(agent_id="hall-seo-intelligence")
    fake = FakeMarketingWorkerAgentBusClient([item])

    response = asyncio.run(run_marketing_worker_once(agent_bus_client=fake, max_items=1))

    assert response.processed == 1
    packet = fake.evidence_packets[0]
    results = packet["test_results"]
    assert results["evidence_type"] == "seo_performance_snapshot"
    assert results["confidence"] == "mock_only"
    assert results["mode"] == "mock_only"
    assert results["mock_mode"] is True
    assert results["live_platform_access"] is False
    assert results["approval_required"] is False
    assert results["not_for_real_marketing_decisions"] is True
    assert "Mock evidence is not for real marketing decisions." in packet["unverified_items"]
    assert fake.attached_evidence[0][1]["evidence_id"] == packet["evidence_id"]


def test_run_once_endpoint_requires_admin_auth() -> None:
    fake = FakeMarketingWorkerAgentBusClient([marketing_work_item()])
    client = client_with_fake_agent_bus(fake, enable_worker=True)

    response = client.post("/api/v1/marketing/workers/mock/run-once", json={"workflow_id": "marketing-wf-test"})

    assert response.status_code == 401


def test_run_once_endpoint_respects_enable_marketing_worker_mock_flag() -> None:
    fake = FakeMarketingWorkerAgentBusClient([marketing_work_item()])
    client = client_with_fake_agent_bus(fake, enable_worker=False)

    response = client.post(
        "/api/v1/marketing/workers/mock/run-once",
        headers={"Authorization": "Bearer admin-token"},
        json={"workflow_id": "marketing-wf-test", "max_items": 4},
    )

    assert response.status_code == 403
    assert "ENABLE_MARKETING_WORKER_MOCK" in response.json()["detail"]
    assert fake.evidence_packets == []


def test_run_once_endpoint_processes_when_enabled() -> None:
    fake = FakeMarketingWorkerAgentBusClient([marketing_work_item()])
    client = client_with_fake_agent_bus(fake, enable_worker=True)

    response = client.post(
        "/api/v1/marketing/workers/mock/run-once",
        headers={"Authorization": "Bearer admin-token"},
        json={"workflow_id": "marketing-wf-test", "max_items": 4},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["workflow_id"] == "marketing-wf-test"
    assert data["processed"] == 1
    assert data["results"][0]["status"] == "completed"
    assert data["results"][0]["mock_mode"] is True
    assert data["results"][0]["live_platform_access"] is False
