from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.clients.agent_bus import AgentBusAPIError
from app.config import Settings, get_settings
from app.main import app
from app.marketing_loop import MARKETING_REPOSITORY, MARKETING_WORKFLOW_TYPE, REVIEW_AGENT
from app.marketing_readonly_evidence import MarketingReadOnlyEvidenceValidationError, attach_read_only_fixture_evidence
from app.marketing_readonly_evidence_contract import AttachReadOnlyFixtureEvidenceRequest
from app.marketing_summary import build_marketing_workflow_summary


class FakeReadOnlyEvidenceAgentBusClient:
    def __init__(self, work_items: list[dict[str, object]] | None = None) -> None:
        self.work_items: list[dict[str, object]] = work_items or []
        self.evidence_packets: dict[str, dict[str, object]] = {}
        self.created_evidence_packets: list[dict[str, object]] = []
        self.attached_evidence: list[tuple[str, dict[str, object]]] = []
        self.external_writes: list[str] = []

    async def list_work_items(self, *, repository: str | None = None) -> list[dict[str, object]]:
        if repository is None:
            return self.work_items
        return [item for item in self.work_items if item.get("repository") == repository]

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

    def add_mock_evidence(self, item: dict[str, object]) -> None:
        evidence_id = f"ev-{uuid4()}"
        packet = {
            "evidence_id": evidence_id,
            "work_item_id": item["work_item_id"],
            "repository": MARKETING_REPOSITORY,
            "implementation_agent": item["owner_agent"],
            "test_results": {
                "evidence_type": "ppc_snapshot",
                "mode": "mock_only",
                "confidence": "mock_only",
                "live_platform_access": False,
            },
        }
        self.evidence_packets[evidence_id] = packet
        metadata = item.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata.setdefault("evidence_packet_ids", []).append(evidence_id)

    def _item(self, work_item_id: str) -> dict[str, object]:
        for item in self.work_items:
            if item.get("work_item_id") == work_item_id:
                return item
        raise AgentBusAPIError("GET", f"/work-items/{work_item_id}", 404, "Work item not found")


def marketing_work_item(
    *,
    agent_id: str = "hall-data-intelligence",
    workflow_id: str = "marketing-wf-readonly",
    live_platform_access: bool = False,
) -> dict[str, object]:
    return {
        "work_item_id": f"wi-{uuid4()}",
        "title": f"Marketing work item: {agent_id}",
        "repository": MARKETING_REPOSITORY,
        "status": "queued",
        "owner_agent": agent_id,
        "review_agent": REVIEW_AGENT,
        "created_at": "2026-06-26T12:00:00Z",
        "updated_at": "2026-06-26T12:00:00Z",
        "metadata": {
            "domain": "marketing",
            "workflow_id": workflow_id,
            "workflow_type": MARKETING_WORKFLOW_TYPE,
            "work_item_role": "specialist_evidence",
            "mock_mode": True,
            "mvp_mode": "mock_only",
            "live_platform_access": live_platform_access,
            "approval_required": True,
        },
    }


def request_payload(work_item_id: str, *, workflow_id: str = "marketing-wf-readonly") -> dict[str, object]:
    return {
        "work_item_id": work_item_id,
        "workflow_id": workflow_id,
        "fixture": {
            "business_unit": "RISE Commercial District",
            "date_range_label": "fixture_last_7_days",
            "website_sessions": 1000,
            "leads": 100,
            "qualified_leads": 40,
            "deals_created": 10,
            "pipeline_value": 25000,
            "closed_won_value": 5000,
            "notes": "Fixture-only weekly marketing snapshot.",
        },
    }


def client_with_fake_agent_bus(fake_client: FakeReadOnlyEvidenceAgentBusClient, *, enable_readonly: bool) -> TestClient:
    get_settings.cache_clear()
    app.dependency_overrides[get_settings] = lambda: Settings(
        github_webhook_secret="test-secret",
        orchestrator_admin_token="admin-token",
        agent_bus_base_url="http://127.0.0.1:8050",
        enable_marketing_readonly_evidence=enable_readonly,
    )
    app.state.agent_bus_client = fake_client
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()
    if hasattr(app.state, "agent_bus_client"):
        delattr(app.state, "agent_bus_client")
    get_settings.cache_clear()


def test_read_only_fixture_endpoint_requires_admin_auth() -> None:
    item = marketing_work_item()
    fake = FakeReadOnlyEvidenceAgentBusClient([item])
    client = client_with_fake_agent_bus(fake, enable_readonly=True)

    response = client.post("/api/v1/marketing/evidence/read-only-fixture/attach", json=request_payload(str(item["work_item_id"])))

    assert response.status_code == 401


def test_read_only_fixture_endpoint_respects_feature_flag() -> None:
    item = marketing_work_item()
    fake = FakeReadOnlyEvidenceAgentBusClient([item])
    client = client_with_fake_agent_bus(fake, enable_readonly=False)

    response = client.post(
        "/api/v1/marketing/evidence/read-only-fixture/attach",
        headers={"Authorization": "Bearer admin-token"},
        json=request_payload(str(item["work_item_id"])),
    )

    assert response.status_code == 403
    assert "ENABLE_MARKETING_READONLY_EVIDENCE" in response.json()["detail"]
    assert fake.created_evidence_packets == []


def test_read_only_fixture_attaches_analytics_snapshot() -> None:
    item = marketing_work_item()
    fake = FakeReadOnlyEvidenceAgentBusClient([item])

    response = asyncio.run(
        attach_read_only_fixture_evidence(
            agent_bus_client=fake,
            payload=AttachReadOnlyFixtureEvidenceRequest(**request_payload(str(item["work_item_id"]))),
        )
    )

    assert response.evidence_type == "analytics_snapshot"
    assert response.source_mode == "read_only_fixture"
    assert response.evidence_packet_id
    packet = fake.created_evidence_packets[0]
    results = packet["test_results"]
    assert isinstance(results, dict)
    assert results["evidence_type"] == "analytics_snapshot"
    assert results["source_mode"] == "read_only_fixture"
    assert fake.attached_evidence[0][1]["evidence_id"] == response.evidence_packet_id


def test_read_only_fixture_calculates_derived_metrics() -> None:
    item = marketing_work_item()
    fake = FakeReadOnlyEvidenceAgentBusClient([item])

    response = asyncio.run(
        attach_read_only_fixture_evidence(
            agent_bus_client=fake,
            payload=AttachReadOnlyFixtureEvidenceRequest(**request_payload(str(item["work_item_id"]))),
        )
    )

    assert response.derived_metrics["lead_conversion_rate"] == 0.1
    assert response.derived_metrics["qualified_lead_rate"] == 0.4
    assert response.derived_metrics["deal_created_rate"] == 0.1
    assert response.derived_metrics["deal_created_per_session_rate"] == 0.01


def test_read_only_fixture_refuses_non_hall_data_agent() -> None:
    item = marketing_work_item(agent_id="hall-ppc-intelligence")
    fake = FakeReadOnlyEvidenceAgentBusClient([item])

    with pytest.raises(MarketingReadOnlyEvidenceValidationError, match="hall-data-intelligence"):
        asyncio.run(
            attach_read_only_fixture_evidence(
                agent_bus_client=fake,
                payload=AttachReadOnlyFixtureEvidenceRequest(**request_payload(str(item["work_item_id"]))),
            )
        )

    assert fake.created_evidence_packets == []


def test_read_only_fixture_refuses_live_platform_work_item() -> None:
    item = marketing_work_item(live_platform_access=True)
    fake = FakeReadOnlyEvidenceAgentBusClient([item])

    with pytest.raises(MarketingReadOnlyEvidenceValidationError, match="live_platform_access=false"):
        asyncio.run(
            attach_read_only_fixture_evidence(
                agent_bus_client=fake,
                payload=AttachReadOnlyFixtureEvidenceRequest(**request_payload(str(item["work_item_id"]))),
            )
        )


def test_read_only_fixture_evidence_includes_safety_fields() -> None:
    item = marketing_work_item()
    fake = FakeReadOnlyEvidenceAgentBusClient([item])

    asyncio.run(
        attach_read_only_fixture_evidence(
            agent_bus_client=fake,
            payload=AttachReadOnlyFixtureEvidenceRequest(**request_payload(str(item["work_item_id"]))),
        )
    )

    results = fake.created_evidence_packets[0]["test_results"]
    assert isinstance(results, dict)
    assert results["source_mode"] == "read_only_fixture"
    assert results["live_platform_access"] is False
    assert results["write_access"] is False
    assert results["not_for_real_marketing_decisions"] is True


def test_summary_counts_read_only_fixture_source_mode() -> None:
    workflow_id = "marketing-wf-readonly"
    data_item = marketing_work_item(workflow_id=workflow_id)
    ppc_item = marketing_work_item(agent_id="hall-ppc-intelligence", workflow_id=workflow_id)
    fake = FakeReadOnlyEvidenceAgentBusClient([data_item, ppc_item])
    fake.add_mock_evidence(ppc_item)
    asyncio.run(
        attach_read_only_fixture_evidence(
            agent_bus_client=fake,
            payload=AttachReadOnlyFixtureEvidenceRequest(**request_payload(str(data_item["work_item_id"]), workflow_id=workflow_id)),
        )
    )

    summary = asyncio.run(
        build_marketing_workflow_summary(
            workflow_id,
            agent_bus_client=fake,
            agent_bus_mission_control_url="/agent-bus",
            orchestrator_snapshot_url="/orchestrator",
        )
    )

    assert summary.evidence_source_modes["read_only_fixture"] == 1
    assert summary.evidence_source_modes["mock_generated"] == 1


def test_read_only_fixture_endpoint_returns_evidence_packet_id() -> None:
    item = marketing_work_item()
    fake = FakeReadOnlyEvidenceAgentBusClient([item])
    client = client_with_fake_agent_bus(fake, enable_readonly=True)

    response = client.post(
        "/api/v1/marketing/evidence/read-only-fixture/attach",
        headers={"Authorization": "Bearer admin-token"},
        json=request_payload(str(item["work_item_id"])),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["evidence_packet_id"]
    assert data["source_mode"] == "read_only_fixture"
    assert data["live_platform_access"] is False
    assert data["write_access"] is False


def test_read_only_fixture_does_not_call_external_writes() -> None:
    item = marketing_work_item()
    fake = FakeReadOnlyEvidenceAgentBusClient([item])

    asyncio.run(
        attach_read_only_fixture_evidence(
            agent_bus_client=fake,
            payload=AttachReadOnlyFixtureEvidenceRequest(**request_payload(str(item["work_item_id"]))),
        )
    )

    assert fake.external_writes == []
