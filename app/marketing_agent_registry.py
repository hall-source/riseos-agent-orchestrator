from __future__ import annotations

from pydantic import BaseModel, Field


class MarketingAgentRegistryEntry(BaseModel):
    agent_id: str
    display_name: str
    agent_type: str
    capabilities: list[str] = Field(default_factory=list)
    default_work_item_roles: list[str] = Field(default_factory=list)
    allowed_evidence_types: list[str] = Field(default_factory=list)
    live_integrations_enabled: bool = False


MARKETING_AGENT_REGISTRY: dict[str, MarketingAgentRegistryEntry] = {
    "clone-banks-hq": MarketingAgentRegistryEntry(
        agent_id="clone-banks-hq",
        display_name="Clone Banks HQ",
        agent_type="orchestration",
        capabilities=["marketing_synthesis", "executive_brief", "human_handoff"],
        default_work_item_roles=["hq_synthesis"],
        allowed_evidence_types=["synthesis_memo"],
    ),
    "hall-data-intelligence": MarketingAgentRegistryEntry(
        agent_id="hall-data-intelligence",
        display_name="Hall Data Intelligence",
        agent_type="marketing_specialist",
        capabilities=["analytics", "measurement", "kpi_summary", "mock_evidence"],
        default_work_item_roles=["specialist", "specialist_evidence"],
        allowed_evidence_types=["analytics_snapshot"],
    ),
    "hall-ppc-intelligence": MarketingAgentRegistryEntry(
        agent_id="hall-ppc-intelligence",
        display_name="Hall PPC Intelligence",
        agent_type="marketing_specialist",
        capabilities=["paid_search", "paid_media", "campaign_analysis", "mock_evidence"],
        default_work_item_roles=["specialist", "specialist_evidence"],
        allowed_evidence_types=["ppc_snapshot"],
    ),
    "hall-seo-intelligence": MarketingAgentRegistryEntry(
        agent_id="hall-seo-intelligence",
        display_name="Hall SEO Intelligence",
        agent_type="marketing_specialist",
        capabilities=["seo", "content_gap", "search_intent", "mock_evidence"],
        default_work_item_roles=["specialist", "specialist_evidence"],
        allowed_evidence_types=["seo_performance_snapshot"],
    ),
    "hall-creative-strategist": MarketingAgentRegistryEntry(
        agent_id="hall-creative-strategist",
        display_name="Hall Creative Strategist",
        agent_type="marketing_specialist",
        capabilities=["creative_strategy", "offer_strategy", "message_testing", "mock_evidence"],
        default_work_item_roles=["specialist", "specialist_evidence"],
        allowed_evidence_types=["creative_strategy_brief"],
    ),
    "hall-marketing-reviewer": MarketingAgentRegistryEntry(
        agent_id="hall-marketing-reviewer",
        display_name="Hall Marketing Reviewer",
        agent_type="review",
        capabilities=["marketing_review", "risk_review", "approval_gate", "human_handoff"],
        default_work_item_roles=["marketing_review"],
        allowed_evidence_types=["risk_review"],
    ),
}

SPECIALIST_AGENT_IDS = tuple(
    agent_id
    for agent_id, entry in MARKETING_AGENT_REGISTRY.items()
    if entry.agent_type == "marketing_specialist"
)


def get_marketing_agent(agent_id: str) -> MarketingAgentRegistryEntry | None:
    return MARKETING_AGENT_REGISTRY.get(agent_id)
