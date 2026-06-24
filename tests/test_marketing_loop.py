from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.clients.agent_bus import AgentBusAPIError
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
        item = {
            **payload,
            "work_item_id": work_item_id,
            "status": "queued",
            "created_at": "2026-06-24T18:00:00+00:00",
            "updated_at": "2026-06-24T18:00:00+00:00",
        }
        self.work_items.append(item)
        return item

    async def list_work_items(self, *, repository: str | None = None) -> list[dict[str, object]]:
        if repository is None:
            return self.work_items
        return [item for item in self.work_items if item.get("repository") == repository]

    async def create_evidence_packet(self, payload: dict[str, object]) -> dict[str, object]:
        evidence_id = str(uuid4())
        packet = {**payload, "evidence_id": evidence_id}
        self.evidence_packets.append(packet)
        return packet

    async def get_evidence_packet(self, evidence_id: str) -> dict[str, object]:
        for packet in self.evidence_packets:
            if packet.get("evidence_id") == evidence_id:
                return packet
        raise AgentBusAPIError("GET", f"/evidence-packets/{evidence_id}", 404, "Evidence packet not found")

    async def attach_evidence_to_work_item(self, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.attached_evidence.append((work_item_id, payload))
        for item in self.work_items:
            if item.get("work_item_id") == work_item_id:
                metadata = item.setdefault("metadata", {})
                if isinstance(metadata, dict):
                    evidence_ids = metadata.setdefault("evidence_packet_ids", [])
                    if isinstance(evidence_ids, list):
                        evidence_ids.append(payload["evidence_id"])
                return item
        return {"work_item_id": work_item_id, "metadata": {"evidence_packet_ids": [payload["evidence_id"]]}}


class UnavailableAgentBusClient(FakeAgentBusClient):
    async def list_work_items(self, *, repository: str | None = None) -> list[dict[str, object]]:
        raise AgentBusAPIError("GET", "/work-items", 503, "Agent Bus unavailable")


def client_with_fake_agent_bus(fake_client: FakeAgentBusClient | None = None) -> tuple[TestClient, FakeAgentBusClient]:
    get_settings.cache_clear()
    app.dependency_overrides[get_settings] = lambda: get_settings().__class__(
        github_webhook_secret="test-secret",
        orchestrator_admin_token="admin-token",
        agent_bus_base_url="http://127.0.0.1:8050",
    )
    fake = fake_client or FakeAgentBusClient()
    app.state.agent_bus_client = fake
    return TestClient(app), fake


def teardown_module() -> None:
    app.dependency_overrides.clear()
    if hasattr(app.state, "agent_bus_client"):
        delattr(app.state, "agent_bus_client")
    get_settings.cache_clear()


def run_mock_workflow(client: TestClient) -> str:
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
    return str(response.json()["workflow_id"])


def work_item_for_role(fake: FakeAgentBusClient, role: str) -> dict[str, object]:
    for item in fake.work_items:
        metadata = item.get("metadata")
        if isinstance(metadata, dict) and metadata.get("work_item_role") == role:
            return item
    raise AssertionError(f"No work item found for role {role}")


def mark_review_complete(fake: FakeAgentBusClient) -> None:
    item = work_item_for_role(fake, "marketing_review")
    metadata = item.setdefault("metadata", {})
    assert isinstance(metadata, dict)
    metadata["review_packet_ids"] = [str(uuid4())]
    item["status"] = "approved"


def mark_synthesis_complete(fake: FakeAgentBusClient) -> None:
    item = work_item_for_role(fake, "hq_synthesis")
    metadata = item.setdefault("metadata", {})
    assert isinstance(metadata, dict)
    metadata["hq_synthesis_packet_ids"] = [str(uuid4())]
    item["status"] = "completed"


def mark_human_approved(fake: FakeAgentBusClient) -> None:
    item = work_item_for_role(fake, "hq_synthesis")
    metadata = item.setdefault("metadata", {})
    assert isinstance(metadata, dict)
    metadata["human_approval_status"] = "approved"


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


def test_marketing_workflow_summary_returns_expected_structure_for_mock_workflow() -> None:
    client, _fake = client_with_fake_agent_bus()
    workflow_id = run_mock_workflow(client)

    response = client.get(
        f"/api/v1/marketing/workflows/{workflow_id}/summary",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["workflow_id"] == workflow_id
    assert data["workflow_type"] == "weekly_marketing_command_brief"
    assert data["domain"] == "marketing"
    assert data["brand"] == "rise"
    assert data["business_unit"] == "RISE Commercial District"
    assert data["source_event"] == "manual_mock_request"
    assert data["requested_by"] == "Hall"
    assert data["human_owner"] == "Hall"
    assert data["approval_required"] is True
    assert data["status"] == "ready_for_review"
    assert len(data["agents"]) == 6
    assert len(data["specialist_work_items"]) == 4
    assert len(data["evidence_packets"]) == 4
    assert data["review"]["review_agent"] == "hall-marketing-reviewer"
    assert data["synthesis"]["agent_id"] == "clone-banks-hq"
    assert data["readiness"]["specialist_evidence_complete"] is True
    assert data["readiness"]["review_complete"] is False
    assert data["readiness"]["synthesis_complete"] is False
    assert data["readiness"]["human_approval_ready"] is False
    assert data["missing"] == ["review_packet", "hq_synthesis_packet", "human_approval"]
    assert data["next_action"] == "Run marketing reviewer or complete mock review packet."
    assert data["links"]["agent_bus_mission_control"] == "http://127.0.0.1:8050/api/v1/mission-control/snapshot"
    assert data["links"]["orchestrator_snapshot"] == "http://127.0.0.1:8055/api/v1/orchestrator/snapshot"

    data_agent = next(agent for agent in data["agents"] if agent["agent_id"] == "hall-data-intelligence")
    assert data_agent["role"] == "specialist"
    assert data_agent["status"] == "completed"
    assert data_agent["evidence_count"] == 1
    assert data_agent["evidence_types"] == ["analytics_snapshot"]


def test_marketing_workflow_summary_missing_workflow_returns_404() -> None:
    client, _fake = client_with_fake_agent_bus()

    response = client.get(
        "/api/v1/marketing/workflows/missing-workflow/summary",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Marketing workflow not found"


def test_marketing_workflow_summary_agent_bus_unavailable_returns_clean_error() -> None:
    client, _fake = client_with_fake_agent_bus(UnavailableAgentBusClient())

    response = client.get(
        "/api/v1/marketing/workflows/marketing-wf-unavailable/summary",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "agent_bus_unavailable"
    assert "Agent Bus" in response.json()["detail"]["message"]


def test_marketing_workflow_summary_readiness_flags_change_when_packets_are_completed() -> None:
    client, fake = client_with_fake_agent_bus()
    workflow_id = run_mock_workflow(client)
    mark_review_complete(fake)
    mark_synthesis_complete(fake)

    response = client.get(
        f"/api/v1/marketing/workflows/{workflow_id}/summary",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "awaiting_human_approval"
    assert data["readiness"] == {
        "specialist_evidence_complete": True,
        "review_complete": True,
        "synthesis_complete": True,
        "human_approval_ready": True,
    }
    assert data["missing"] == ["human_approval"]
    assert data["next_action"] == "Hall review is ready for human approval."


def test_marketing_workflow_summary_next_action_reaches_completed_after_human_approval() -> None:
    client, fake = client_with_fake_agent_bus()
    workflow_id = run_mock_workflow(client)
    mark_review_complete(fake)
    mark_synthesis_complete(fake)
    mark_human_approved(fake)

    response = client.get(
        f"/api/v1/marketing/workflows/{workflow_id}/summary",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["readiness"]["human_approval_ready"] is False
    assert data["missing"] == []
    assert data["next_action"] == "Marketing workflow summary is complete."
