from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from app.clients.agent_bus import AgentBusAPIError
from app.config import Settings, get_settings
from app.main import app
from app.marketing_executive_brief_builder import build_weekly_marketing_executive_brief
from app.marketing_loop import MARKETING_REPOSITORY, MARKETING_WORKFLOW_TYPE, REVIEW_AGENT, SPECIALIST_AGENTS, SYNTHESIS_AGENT
from app.marketing_summary import build_marketing_workflow_summary


class FakeExecutiveBriefAgentBusClient:
    def __init__(self, *, include_analytics: bool = True, approved: bool = False) -> None:
        self.workflow_id = f"marketing-wf-{uuid4()}"
        self.work_items: list[dict[str, object]] = []
        self.evidence_packets: dict[str, dict[str, object]] = {}
        self.external_writes: list[str] = []
        self.created_evidence_packets: list[dict[str, object]] = []
        self._seed_workflow(include_analytics=include_analytics, approved=approved)

    async def list_work_items(self, *, repository: str | None = None) -> list[dict[str, object]]:
        if repository is None:
            return self.work_items
        return [item for item in self.work_items if item.get("repository") == repository]

    async def get_evidence_packet(self, evidence_id: str) -> dict[str, object]:
        try:
            return self.evidence_packets[evidence_id]
        except KeyError as exc:
            raise AgentBusAPIError("GET", f"/evidence-packets/{evidence_id}", 404, "Evidence packet not found") from exc

    def human_approval_count(self) -> int:
        return sum(1 for packet in self.evidence_packets.values() if _packet_type(packet) == "human_approval")

    def _seed_workflow(self, *, include_analytics: bool, approved: bool) -> None:
        for agent_id in SPECIALIST_AGENTS:
            item = self._work_item(agent_id, "specialist_evidence", status="completed")
            evidence_type = "analytics_snapshot" if agent_id == "hall-data-intelligence" and include_analytics else "mock_specialist_snapshot"
            content = _analytics_content() if evidence_type == "analytics_snapshot" else _mock_specialist_content(agent_id, evidence_type)
            self._attach_packet(item, content, implementation_agent=agent_id)
            self.work_items.append(item)

        review_item = self._work_item(REVIEW_AGENT, "marketing_review", status="completed")
        self._attach_packet(
            review_item,
            {
                "artifact_type": "risk_review",
                "evidence_type": "risk_review",
                "produced_by": REVIEW_AGENT,
                "workflow_id": self.workflow_id,
                "approval_recommendation": "ready_for_hq_synthesis_mock_only",
                "risk_flags": ["mock_only_no_business_decisions"],
                "confidence": "mock_only",
                "live_platform_access": False,
                "not_for_real_marketing_decisions": True,
            },
            implementation_agent=REVIEW_AGENT,
        )
        self.work_items.append(review_item)

        synthesis_item = self._work_item(SYNTHESIS_AGENT, "hq_synthesis", status="completed")
        synthesis_packet = self._attach_packet(
            synthesis_item,
            {
                "artifact_type": "synthesis_memo",
                "evidence_type": "synthesis_memo",
                "produced_by": SYNTHESIS_AGENT,
                "workflow_id": self.workflow_id,
                "approval_status": "awaiting_human_approval_mock_only",
                "summary": "Mock Weekly Marketing Command Brief synthesized from worker-produced mock specialist evidence and mock reviewer packet.",
                "confidence": "mock_only",
                "live_platform_access": False,
                "not_for_real_marketing_decisions": True,
            },
            implementation_agent=SYNTHESIS_AGENT,
        )
        if approved:
            self._attach_packet(
                synthesis_item,
                {
                    "artifact_type": "human_approval",
                    "evidence_type": "human_approval",
                    "workflow_id": self.workflow_id,
                    "decision": "approve_mock",
                    "approval_state": "approved_mock_only",
                    "approved_by": "Hall",
                    "notes": "Executive brief endpoint validated. No production action authorized.",
                    "approved_artifact_id": synthesis_packet["evidence_id"],
                    "approved_artifact_type": "synthesis_memo",
                    "mock_mode": True,
                    "confidence": "mock_only",
                    "live_platform_access": False,
                    "no_production_write_performed": True,
                    "no_external_platform_action_performed": True,
                    "not_for_real_marketing_decisions": True,
                    "created_at": "2026-06-30T12:00:00Z",
                },
                implementation_agent="Hall",
            )
        self.work_items.append(synthesis_item)

    def _work_item(self, owner_agent: str, role: str, *, status: str) -> dict[str, object]:
        return {
            "work_item_id": f"wi-{uuid4()}",
            "title": f"Marketing work item: {owner_agent}",
            "repository": MARKETING_REPOSITORY,
            "status": status,
            "owner_agent": owner_agent,
            "review_agent": REVIEW_AGENT,
            "created_at": "2026-06-30T12:00:00Z",
            "updated_at": "2026-06-30T12:00:00Z",
            "metadata": {
                "domain": "marketing",
                "brand": "rise",
                "business_unit": "RISE Commercial District",
                "workflow_id": self.workflow_id,
                "workflow_type": MARKETING_WORKFLOW_TYPE,
                "work_item_role": role,
                "requested_by": "Hall",
                "human_owner": "Hall",
                "mock_mode": True,
                "mvp_mode": "mock_only",
                "live_platform_access": False,
                "approval_required": True,
            },
        }

    def _attach_packet(
        self,
        item: dict[str, object],
        content: dict[str, object],
        *,
        implementation_agent: str,
    ) -> dict[str, object]:
        evidence_id = f"ev-{uuid4()}"
        packet = {
            "evidence_id": evidence_id,
            "work_item_id": item["work_item_id"],
            "repository": MARKETING_REPOSITORY,
            "implementation_agent": implementation_agent,
            "branch": "agent-integration",
            "commit_shas": [],
            "changed_files": [],
            "test_commands": ["marketing-executive-brief-test-fixture"],
            "test_results": content,
            "verification_summary": "Executive brief test fixture.",
        }
        self.evidence_packets[evidence_id] = packet
        metadata = item.setdefault("metadata", {})
        assert isinstance(metadata, dict)
        metadata.setdefault("evidence_packet_ids", []).append(evidence_id)
        return packet


class EmptyExecutiveBriefAgentBusClient:
    async def list_work_items(self, *, repository: str | None = None) -> list[dict[str, object]]:
        return []

    async def get_evidence_packet(self, evidence_id: str) -> dict[str, object]:
        raise AssertionError("No evidence should be read when workflow is missing")


def _analytics_content() -> dict[str, object]:
    return {
        "artifact_type": "analytics_snapshot",
        "evidence_type": "analytics_snapshot",
        "produced_by": "hall-data-intelligence",
        "workflow_id": "marketing-wf-test",
        "source_mode": "google_sheets_readonly",
        "date_range_label": "last_7_days",
        "metrics": {
            "leads": 42,
            "contacts_created": 38,
            "deals_created": 6,
            "sessions": 1200,
            "deal_created_rate_from_leads": 0.1429,
        },
        "source_breakdown": [
            {"source": "paid_search", "leads": 18, "contacts_created": 16, "deals_created": 3, "sessions": 450},
            {"source": "organic_search", "leads": 14, "contacts_created": 12, "deals_created": 2, "sessions": 500},
            {"source": "direct", "leads": 10, "contacts_created": 10, "deals_created": 1, "sessions": 250},
        ],
        "findings": [
            "Read-only source reported 42 leads and 6 deals created.",
            "Deal-created rate from leads is 0.1429.",
        ],
        "confidence": "read_only_source",
        "live_platform_access": False,
        "write_access": False,
        "not_for_real_marketing_decisions": True,
        "approval_required": False,
    }


def _mock_specialist_content(agent_id: str, evidence_type: str) -> dict[str, object]:
    return {
        "artifact_type": evidence_type,
        "evidence_type": evidence_type,
        "produced_by": agent_id,
        "workflow_id": "marketing-wf-test",
        "confidence": "mock_only",
        "mode": "mock_only",
        "mock_mode": True,
        "live_platform_access": False,
        "not_for_real_marketing_decisions": True,
    }


def _packet_type(packet: dict[str, object]) -> str | None:
    content = packet.get("test_results")
    if not isinstance(content, dict):
        return None
    value = content.get("artifact_type") or content.get("evidence_type")
    return str(value) if value else None


def _summary_from_fake(fake: FakeExecutiveBriefAgentBusClient):
    return asyncio.run(
        build_marketing_workflow_summary(
            fake.workflow_id,
            agent_bus_client=fake,
            agent_bus_mission_control_url="http://127.0.0.1:8050/api/v1/mission-control/snapshot",
            orchestrator_snapshot_url="http://127.0.0.1:8055/api/v1/orchestrator/snapshot",
        )
    )


def client_with_fake_agent_bus(fake: object, *, enable_brief: bool = True) -> TestClient:
    get_settings.cache_clear()
    app.dependency_overrides[get_settings] = lambda: Settings(
        github_webhook_secret="test-secret",
        orchestrator_admin_token="admin-token",
        agent_bus_base_url="http://127.0.0.1:8050",
        enable_weekly_marketing_executive_brief=enable_brief,
    )
    app.state.agent_bus_client = fake
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()
    if hasattr(app.state, "agent_bus_client"):
        delattr(app.state, "agent_bus_client")
    get_settings.cache_clear()


def test_executive_brief_builder_maps_deterministic_content_channels_and_risks() -> None:
    fake = FakeExecutiveBriefAgentBusClient(approved=False)
    brief = build_weekly_marketing_executive_brief(_summary_from_fake(fake))

    assert brief.executive_summary.headline == "Weekly marketing snapshot is ready for review."
    assert brief.scorecard == {
        "leads": 42,
        "contacts_created": 38,
        "deals_created": 6,
        "sessions": 1200,
        "deal_created_rate_from_leads": 0.1429,
    }
    assert brief.channel_breakdown[0] == {
        "source": "paid_search",
        "leads": 18,
        "contacts_created": 16,
        "deals_created": 3,
        "sessions": 450,
    }
    assert brief.findings == [
        "Read-only source reported 42 leads and 6 deals created.",
        "Deal-created rate from leads is 0.1429.",
    ]
    assert brief.review.risk_flags == ["mock_only_no_business_decisions"]
    assert brief.review.approval_recommendation == "ready_for_hq_synthesis_mock_only"
    assert brief.recommended_next_action == "Hall should review the synthesis and approve or request changes."


def test_executive_brief_builder_maps_approved_guidance() -> None:
    fake = FakeExecutiveBriefAgentBusClient(approved=True)
    brief = build_weekly_marketing_executive_brief(_summary_from_fake(fake))

    assert brief.status == "completed"
    assert brief.approval_state == "approved_mock_only"
    assert brief.human_approval_complete is True
    assert brief.executive_summary.headline == "Weekly marketing snapshot has been approved."
    assert brief.recommended_next_action == "Mock workflow has been validated. No production action has been authorized."


def test_executive_brief_builder_returns_partial_brief_without_analytics() -> None:
    fake = FakeExecutiveBriefAgentBusClient(include_analytics=False)
    brief = build_weekly_marketing_executive_brief(_summary_from_fake(fake))

    assert brief.scorecard == {}
    assert brief.channel_breakdown == []
    assert brief.findings == ["Analytics snapshot evidence is not available for this workflow."]


def test_executive_brief_feature_flag_disabled_returns_403_without_mutation() -> None:
    fake = FakeExecutiveBriefAgentBusClient()
    before_approval_count = fake.human_approval_count()
    client = client_with_fake_agent_bus(fake, enable_brief=False)

    response = client.get(
        f"/api/v1/marketing/workflows/{fake.workflow_id}/executive-brief",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 403
    assert fake.human_approval_count() == before_approval_count
    assert fake.created_evidence_packets == []
    assert fake.external_writes == []


def test_executive_brief_requires_admin_auth() -> None:
    fake = FakeExecutiveBriefAgentBusClient()
    client = client_with_fake_agent_bus(fake)

    response = client.get(f"/api/v1/marketing/workflows/{fake.workflow_id}/executive-brief")

    assert response.status_code == 401


def test_executive_brief_workflow_not_found_returns_404() -> None:
    client = client_with_fake_agent_bus(EmptyExecutiveBriefAgentBusClient())

    response = client.get(
        "/api/v1/marketing/workflows/missing-workflow/executive-brief",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Marketing workflow not found"


def test_executive_brief_pre_approval_reflects_review_required() -> None:
    fake = FakeExecutiveBriefAgentBusClient(approved=False)
    client = client_with_fake_agent_bus(fake)

    response = client.get(
        f"/api/v1/marketing/workflows/{fake.workflow_id}/executive-brief",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_id"] == fake.workflow_id
    assert body["brief_type"] == "weekly_marketing_executive_brief"
    assert body["business_unit"] == "RISE Commercial District"
    assert body["date_range_label"] == "last_7_days"
    assert body["status"] == "awaiting_human_approval"
    assert body["approval_state"] == "not_approved"
    assert body["approval_required"] is True
    assert body["human_approval_complete"] is False
    assert body["executive_summary"]["headline"] == "Weekly marketing snapshot is ready for review."
    assert body["review"]["ready"] is True
    assert body["review"]["risk_flags"] == ["mock_only_no_business_decisions"]
    assert body["synthesis"]["ready"] is True
    assert body["recommended_next_action"] == "Hall should review the synthesis and approve or request changes."
    assert body["links"]["summary_url"] == f"/api/v1/marketing/workflows/{fake.workflow_id}/summary"
    assert body["links"]["audit_events_url"] == f"/api/v1/marketing/evidence/audit?workflow_id={fake.workflow_id}"
    assert body["links"]["approval_url"] == f"/api/v1/marketing/workflows/{fake.workflow_id}/approval"


def test_executive_brief_post_approval_reflects_completed_state() -> None:
    fake = FakeExecutiveBriefAgentBusClient(approved=True)
    client = client_with_fake_agent_bus(fake)

    response = client.get(
        f"/api/v1/marketing/workflows/{fake.workflow_id}/executive-brief",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["approval_state"] == "approved_mock_only"
    assert body["human_approval_complete"] is True
    assert body["executive_summary"]["headline"] == "Weekly marketing snapshot has been approved."
    assert body["recommended_next_action"] == "Mock workflow has been validated. No production action has been authorized."


def test_executive_brief_extracts_analytics_snapshot() -> None:
    fake = FakeExecutiveBriefAgentBusClient()
    client = client_with_fake_agent_bus(fake)

    response = client.get(
        f"/api/v1/marketing/workflows/{fake.workflow_id}/executive-brief",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["scorecard"] == {
        "leads": 42,
        "contacts_created": 38,
        "deals_created": 6,
        "sessions": 1200,
        "deal_created_rate_from_leads": 0.1429,
    }
    assert body["channel_breakdown"][0] == {
        "source": "paid_search",
        "leads": 18,
        "contacts_created": 16,
        "deals_created": 3,
        "sessions": 450,
    }
    assert body["findings"] == [
        "Read-only source reported 42 leads and 6 deals created.",
        "Deal-created rate from leads is 0.1429.",
    ]


def test_executive_brief_missing_analytics_returns_partial_brief() -> None:
    fake = FakeExecutiveBriefAgentBusClient(include_analytics=False)
    client = client_with_fake_agent_bus(fake)

    response = client.get(
        f"/api/v1/marketing/workflows/{fake.workflow_id}/executive-brief",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["scorecard"] == {}
    assert body["channel_breakdown"] == []
    assert body["findings"] == ["Analytics snapshot evidence is not available for this workflow."]


def test_executive_brief_safety_flags_are_false_for_live_and_write_access() -> None:
    fake = FakeExecutiveBriefAgentBusClient()
    client = client_with_fake_agent_bus(fake)

    response = client.get(
        f"/api/v1/marketing/workflows/{fake.workflow_id}/executive-brief",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["live_platform_access"] is False
    assert body["write_access"] is False
    assert body["not_for_real_marketing_decisions"] is True


def test_executive_brief_does_not_auto_approve_or_mutate_state() -> None:
    fake = FakeExecutiveBriefAgentBusClient(approved=False)
    before_approval_count = fake.human_approval_count()
    before_packet_count = len(fake.evidence_packets)
    client = client_with_fake_agent_bus(fake)

    first = client.get(
        f"/api/v1/marketing/workflows/{fake.workflow_id}/executive-brief",
        headers={"Authorization": "Bearer admin-token"},
    )
    second = client.get(
        f"/api/v1/marketing/workflows/{fake.workflow_id}/executive-brief",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["approval_state"] == "not_approved"
    assert second.json()["approval_state"] == "not_approved"
    assert fake.human_approval_count() == before_approval_count
    assert len(fake.evidence_packets) == before_packet_count
    assert fake.created_evidence_packets == []
    assert fake.external_writes == []
