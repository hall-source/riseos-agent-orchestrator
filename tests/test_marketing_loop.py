from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


class FakeAgentBusClient:
    def __init__(self) -> None:
        self.registered_agents: list[dict[str, object]] = []
        self.heartbeats: list[dict[str, object]] = []
        self.work_items: list[dict[str, object]] = []
        self.evidence_packets: list[dict[str, object]] = []
        self.attached_evidence: list[tuple[str, dict[str, object]]] = []

    async def register_agent(self, payload: dict[str, object]) -> dict[str, object]:
        self.registered_agents.append(payload)
        return payload

    async def heartbeat_agent(self, payload: dict[str, object]) -> dict[str, object]:
        self.heartbeats.append(payload)
        return payload

    async def create_work_item(self, payload: dict[str, object]) -> dict[str, object]:
        work_item_id = str(uuid4())
        self.work_items.append({**payload, "work_item_id": work_item_id})
        return {"work_item_id": work_item_id, **payload}

    async def create_evidence_packet(self, payload: dict[str, object]) -> dict[str, object]:
        evidence_id = str(uuid4())
        self.evidence_packets.append({**payload, "evidence_id": evidence_id})
        return {"evidence_id": evidence_id, **payload}

    async def attach_evidence_to_work_item(self, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.attached_evidence.append((work_item_id, payload))
        return {"work_item_id": work_item_id, "metadata": {"evidence_packet_ids": [payload["evidence_id"]]}}


def client_with_fake_agent_bus() -> tuple[TestClient, FakeAgentBusClient]:
    get_settings.cache_clear()
    app.dependency_overrides[get_settings] = lambda: get_settings().__class__(
        github_webhook_secret="test-secret",
        orchestrator_admin_token="admin-token",
        agent_bus_base_url="http://127.0.0.1:8050",
    )
    fake_client = FakeAgentBusClient()
    app.state.agent_bus_client = fake_client
    return TestClient(app), fake_client


def teardown_module() -> None:
    app.dependency_overrides.clear()
    if hasattr(app.state, "agent_bus_client"):
        delattr(app.state, "agent_bus_client")
    get_settings.cache_clear()


def test_mock_weekly_marketing_command_brief_requires_admin_token() -> None:
    client, _fake = client_with_fake_agent_bus()

    response = client.post("/api/v1/marketing/weekly-command-brief/mock-run", json={})

    assert response.status_code == 401


def test_mock_weekly_marketing_command_brief_creates_mock_loop_with_bearer_token() -> None:
    client, fake = client_with_fake_agent_bus()

    response = client.post(
        "/api/v1/marketing/weekly-command-brief/mock-run",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "business_unit": "RISE Commercial District",
            "requested_by": "Hall",
            "date_range_label": "mock_last_7_days",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "mock_loop_created"
    assert data["workflow_id"].startswith("marketing-wf-")
    assert data["mission_control_url"] == "http://127.0.0.1:8050/api/v1/mission-control/snapshot"
    assert len(data["created_agents"]) == 6
    assert len(data["created_work_items"]) == 6
    assert len(data["created_evidence_packets"]) == 4
    assert data["review_item_id"] in data["created_work_items"]
    assert data["synthesis_item_id"] in data["created_work_items"]

    assert len(fake.registered_agents) == 6
    assert len(fake.heartbeats) == 6
    assert len(fake.work_items) == 6
    assert len(fake.evidence_packets) == 4
    assert len(fake.attached_evidence) == 4
    assert {item["owner_agent"] for item in fake.work_items[:4]} == {
        "hall-data-intelligence",
        "hall-ppc-intelligence",
        "hall-seo-intelligence",
        "hall-creative-strategist",
    }

    metadata = fake.work_items[0]["metadata"]
    assert metadata["domain"] == "marketing"
    assert metadata["brand"] == "rise"
    assert metadata["business_unit"] == "RISE Commercial District"
    assert metadata["workflow_type"] == "weekly_marketing_command_brief"
    assert metadata["source_event"] == "manual_mock_request"
    assert metadata["approval_required"] is True
    assert metadata["human_owner"] == "Hall"
    assert metadata["review_agent"] == "hall-marketing-reviewer"
    assert metadata["live_platform_access"] is False

    evidence = fake.evidence_packets[0]["test_results"]
    assert evidence["mode"] == "mock_only"
    assert evidence["confidence"] == "mock_only"
    assert evidence["live_platform_access"] is False


def test_mock_weekly_marketing_command_brief_accepts_existing_admin_header() -> None:
    client, _fake = client_with_fake_agent_bus()

    response = client.post(
        "/api/v1/marketing/weekly-command-brief/mock-run",
        headers={"X-Orchestrator-Admin-Token": "admin-token"},
        json={},
    )

    assert response.status_code == 200
