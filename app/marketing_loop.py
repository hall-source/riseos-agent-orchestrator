from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from app.clients.agent_bus import AgentBusAPIError

MARKETING_REPOSITORY = "hall-source/riseos-agent-orchestrator"
MARKETING_WORKFLOW_TYPE = "weekly_marketing_command_brief"
MARKETING_SOURCE_EVENT = "manual_mock_request"
REVIEW_AGENT = "hall-marketing-reviewer"
SYNTHESIS_AGENT = "clone-banks-hq"
SPECIALIST_AGENTS = [
    "hall-data-intelligence",
    "hall-ppc-intelligence",
    "hall-seo-intelligence",
    "hall-creative-strategist",
]

MARKETING_AGENTS: list[dict[str, Any]] = [
    {
        "agent_id": SYNTHESIS_AGENT,
        "agent_type": "orchestration",
        "capabilities": ["marketing_synthesis", "executive_brief", "human_handoff"],
    },
    {
        "agent_id": "hall-data-intelligence",
        "agent_type": "marketing_specialist",
        "capabilities": ["analytics", "measurement", "kpi_summary", "mock_evidence"],
    },
    {
        "agent_id": "hall-ppc-intelligence",
        "agent_type": "marketing_specialist",
        "capabilities": ["paid_search", "paid_media", "campaign_analysis", "mock_evidence"],
    },
    {
        "agent_id": "hall-seo-intelligence",
        "agent_type": "marketing_specialist",
        "capabilities": ["seo", "content_gap", "search_intent", "mock_evidence"],
    },
    {
        "agent_id": "hall-creative-strategist",
        "agent_type": "marketing_specialist",
        "capabilities": ["creative_strategy", "offer_strategy", "message_testing", "mock_evidence"],
    },
    {
        "agent_id": REVIEW_AGENT,
        "agent_type": "review",
        "capabilities": ["marketing_review", "risk_review", "approval_gate", "human_handoff"],
    },
]

MOCK_EVIDENCE_BY_AGENT: dict[str, dict[str, Any]] = {
    "hall-data-intelligence": {
        "evidence_type": "analytics_snapshot",
        "produced_by": "hall-data-intelligence",
        "summary": "Mock data shows total leads increased while deal-created rate requires review.",
        "findings": [
            "Lead volume increased in the mock period.",
            "Deal-created quality is marked as unknown because no live HubSpot data was used.",
        ],
        "confidence": "mock_only",
        "sources_checked": ["mock_ga4", "mock_hubspot"],
        "approval_required": False,
    },
    "hall-ppc-intelligence": {
        "evidence_type": "ppc_snapshot",
        "produced_by": "hall-ppc-intelligence",
        "summary": "Mock PPC review flags paid search efficiency as a follow-up area.",
        "findings": [
            "Mock spend efficiency requires review.",
            "No real Google Ads data was accessed.",
        ],
        "confidence": "mock_only",
        "sources_checked": ["mock_google_ads"],
        "approval_required": False,
    },
    "hall-seo-intelligence": {
        "evidence_type": "seo_performance_snapshot",
        "produced_by": "hall-seo-intelligence",
        "summary": "Mock SEO review identifies city page opportunity areas.",
        "findings": [
            "Mock query/page gap found for city pages.",
            "No real Search Console data was accessed.",
        ],
        "confidence": "mock_only",
        "sources_checked": ["mock_search_console"],
        "approval_required": False,
    },
    "hall-creative-strategist": {
        "evidence_type": "creative_strategy_brief",
        "produced_by": "hall-creative-strategist",
        "summary": "Mock creative review suggests testing clearer offer/message alignment.",
        "findings": [
            "Mock funnel evidence suggests offer clarity may improve conversion.",
            "No real ad or landing page assets were accessed.",
        ],
        "confidence": "mock_only",
        "sources_checked": ["mock_prior_findings"],
        "approval_required": False,
    },
}


class MarketingAgentBusClient(Protocol):
    async def register_agent(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def heartbeat_agent(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def create_work_item(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def create_evidence_packet(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def attach_evidence_to_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class MockWeeklyMarketingBriefRequest(BaseModel):
    brand: str = "rise"
    business_unit: str = "RISE Commercial District"
    requested_by: str = "Hall"
    date_range_label: str = "mock_last_7_days"


class MockWeeklyMarketingBriefResponse(BaseModel):
    workflow_id: str
    created_agents: list[str] = Field(default_factory=list)
    created_work_items: list[str] = Field(default_factory=list)
    created_evidence_packets: list[str] = Field(default_factory=list)
    review_item_id: str
    synthesis_item_id: str
    mission_control_url: str
    status: str = "mock_loop_created"


@dataclass(frozen=True)
class MockMarketingLoopContext:
    workflow_id: str
    brand: str
    business_unit: str
    requested_by: str
    date_range_label: str
    human_owner: str = "Hall"

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "domain": "marketing",
            "brand": self.brand,
            "business_unit": self.business_unit,
            "workflow_type": MARKETING_WORKFLOW_TYPE,
            "source_event": MARKETING_SOURCE_EVENT,
            "approval_required": True,
            "human_owner": self.human_owner,
            "review_agent": REVIEW_AGENT,
            "requested_by": self.requested_by,
            "date_range_label": self.date_range_label,
            "workflow_id": self.workflow_id,
            "mvp_mode": "mock_only",
            "live_platform_access": False,
        }


async def create_mock_weekly_marketing_command_brief(
    request: MockWeeklyMarketingBriefRequest,
    *,
    agent_bus_client: MarketingAgentBusClient,
    mission_control_url: str,
) -> MockWeeklyMarketingBriefResponse:
    context = MockMarketingLoopContext(
        workflow_id=f"marketing-wf-{uuid4()}",
        brand=request.brand,
        business_unit=request.business_unit,
        requested_by=request.requested_by,
        date_range_label=request.date_range_label,
    )
    created_agents = await _seed_marketing_agents(agent_bus_client, context)
    specialist_item_ids: dict[str, str] = {}
    created_evidence_packets: list[str] = []

    for agent_id in SPECIALIST_AGENTS:
        work_item = await agent_bus_client.create_work_item(_specialist_work_item_payload(agent_id, context))
        work_item_id = _response_id(work_item, "work_item_id")
        specialist_item_ids[agent_id] = work_item_id
        evidence = await agent_bus_client.create_evidence_packet(_evidence_packet_payload(agent_id, work_item_id, context))
        evidence_id = _response_id(evidence, "evidence_id")
        created_evidence_packets.append(evidence_id)
        await agent_bus_client.attach_evidence_to_work_item(
            work_item_id,
            {"evidence_id": evidence_id, "actor": "riseos-agent-orchestrator"},
        )

    review_item = await agent_bus_client.create_work_item(_review_work_item_payload(specialist_item_ids, context))
    review_item_id = _response_id(review_item, "work_item_id")
    synthesis_item = await agent_bus_client.create_work_item(_synthesis_work_item_payload(specialist_item_ids, review_item_id, context))
    synthesis_item_id = _response_id(synthesis_item, "work_item_id")

    return MockWeeklyMarketingBriefResponse(
        workflow_id=context.workflow_id,
        created_agents=created_agents,
        created_work_items=[*specialist_item_ids.values(), review_item_id, synthesis_item_id],
        created_evidence_packets=created_evidence_packets,
        review_item_id=review_item_id,
        synthesis_item_id=synthesis_item_id,
        mission_control_url=mission_control_url,
    )


async def _seed_marketing_agents(client: MarketingAgentBusClient, context: MockMarketingLoopContext) -> list[str]:
    seeded_agents: list[str] = []
    for agent in MARKETING_AGENTS:
        agent_id = str(agent["agent_id"])
        payload = {
            **agent,
            "status": "online",
            "health_state": "healthy",
            "availability": "available",
            "metadata": {
                **context.metadata,
                "agent_seeded_by": "riseos-agent-orchestrator",
                "agent_id": agent_id,
            },
        }
        try:
            await client.register_agent(payload)
        except AgentBusAPIError as exc:
            if exc.status_code != 409:
                raise
        await client.heartbeat_agent(
            {
                "agent_id": agent_id,
                "status": "online",
                "health_state": "healthy",
                "availability": "available",
                "metadata": payload["metadata"],
            }
        )
        seeded_agents.append(agent_id)
    return seeded_agents


def _specialist_work_item_payload(agent_id: str, context: MockMarketingLoopContext) -> dict[str, Any]:
    evidence = MOCK_EVIDENCE_BY_AGENT[agent_id]
    return {
        "title": f"Mock Weekly Marketing Command Brief: {agent_id}",
        "repository": MARKETING_REPOSITORY,
        "priority": "normal",
        "owner_agent": agent_id,
        "review_agent": REVIEW_AGENT,
        "metadata": {
            **context.metadata,
            "work_item_role": "specialist_evidence",
            "specialist_agent": agent_id,
            "mock_evidence_summary": evidence["summary"],
        },
    }


def _review_work_item_payload(specialist_item_ids: dict[str, str], context: MockMarketingLoopContext) -> dict[str, Any]:
    return {
        "title": "Mock Weekly Marketing Command Brief: Hall reviewer approval gate",
        "repository": MARKETING_REPOSITORY,
        "priority": "normal",
        "owner_agent": REVIEW_AGENT,
        "review_agent": REVIEW_AGENT,
        "metadata": {
            **context.metadata,
            "work_item_role": "marketing_review",
            "depends_on_work_item_ids": list(specialist_item_ids.values()),
            "approval_required": True,
            "live_platform_access": False,
        },
    }


def _synthesis_work_item_payload(specialist_item_ids: dict[str, str], review_item_id: str, context: MockMarketingLoopContext) -> dict[str, Any]:
    return {
        "title": "Mock Weekly Marketing Command Brief: Clone Banks HQ synthesis",
        "repository": MARKETING_REPOSITORY,
        "priority": "normal",
        "owner_agent": SYNTHESIS_AGENT,
        "review_agent": REVIEW_AGENT,
        "metadata": {
            **context.metadata,
            "work_item_role": "hq_synthesis",
            "depends_on_work_item_ids": [*specialist_item_ids.values(), review_item_id],
            "review_item_id": review_item_id,
            "approval_required": True,
            "live_platform_access": False,
        },
    }


def _evidence_packet_payload(agent_id: str, work_item_id: str, context: MockMarketingLoopContext) -> dict[str, Any]:
    evidence = MOCK_EVIDENCE_BY_AGENT[agent_id]
    return {
        "work_item_id": work_item_id,
        "repository": MARKETING_REPOSITORY,
        "implementation_agent": agent_id,
        "branch": "agent-integration",
        "commit_shas": [],
        "changed_files": [],
        "test_commands": ["mock-marketing-loop"],
        "test_results": {
            "mode": "mock_only",
            "source_systems": evidence["sources_checked"],
            "live_platform_access": False,
            "evidence_schema": "marketing.mock_evidence.v1",
            "marketing_metadata": context.metadata,
            **evidence,
        },
        "verification_summary": evidence["summary"],
        "assumptions": ["No live marketing platform data was used."],
        "unverified_items": ["Live marketing source data is intentionally not connected in this MVP."],
    }


def _response_id(response: dict[str, Any], key: str) -> str:
    value = response.get(key) or response.get("id")
    if not value:
        raise ValueError(f"Agent Bus response did not include {key}.")
    return str(value)
