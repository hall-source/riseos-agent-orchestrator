# Marketing Agent Registry

## Purpose

The Marketing Agent Registry defines the stable IDs, roles, capabilities, and metadata for the first marketing workflow agents. Agent Bus already owns the canonical agent registry, so the MVP should seed these records through Agent Bus instead of creating a separate registry table.

## Required MVP Agents

| Agent ID | Agent type | Primary role | Suggested capabilities |
|---|---|---|---|
| `clone-banks-hq` | `orchestration` | Synthesizes final weekly marketing command brief | `marketing_synthesis`, `executive_brief`, `cross_channel_prioritization`, `human_handoff` |
| `hall-data-intelligence` | `marketing_specialist` | Summarizes performance, measurement, anomalies, and data-quality caveats | `analytics`, `measurement`, `kpi_summary`, `mock_evidence` |
| `hall-ppc-intelligence` | `marketing_specialist` | Reviews paid media posture and PPC recommendations | `paid_search`, `paid_media`, `campaign_analysis`, `mock_evidence` |
| `hall-seo-intelligence` | `marketing_specialist` | Reviews organic search and content demand opportunities | `seo`, `content_gap`, `search_intent`, `mock_evidence` |
| `hall-creative-strategist` | `marketing_specialist` | Reviews offers, messaging, creative angles, and experiment ideas | `creative_strategy`, `offer_strategy`, `message_testing`, `mock_evidence` |
| `hall-marketing-reviewer` | `review` | Reviews specialist evidence and prepares human approval handoff | `marketing_review`, `risk_review`, `approval_gate`, `human_handoff` |

## Agent Bus Registration Payloads

Each agent can be seeded with `POST /agents`.

```json
{
  "agent_id": "hall-data-intelligence",
  "agent_type": "marketing_specialist",
  "capabilities": ["analytics", "measurement", "kpi_summary", "mock_evidence"],
  "status": "online",
  "health_state": "healthy",
  "availability": "available",
  "metadata": {
    "domain": "marketing",
    "brand_scope": ["rise"],
    "business_unit_scope": ["RISE Commercial District"],
    "mvp_mode": "mock_only",
    "live_platform_access": false
  }
}
```

## Registry Seed Method

For the first implementation PR, add an idempotent seed helper in the orchestrator rather than a new CLI.

Recommended helper shape:

```python
async def ensure_marketing_agents(agent_bus: AgentBusClient) -> list[dict[str, Any]]:
    """Register or update the MVP marketing agents in Agent Bus."""
```

Expected behavior:

1. Attempt to register each required agent with `POST /agents`.
2. Treat HTTP 409 duplicate-agent responses as success.
3. Optionally send a heartbeat after registration to refresh presence.
4. Return a list of agent IDs and seed outcomes for the endpoint response.

## Why Seed From Orchestrator

The orchestrator owns workflow initiation. Seeding the required agents as part of the manual mock run ensures local/Vultr validation starts from a clean Agent Bus database and still produces a visible Mission Control snapshot.

## Registry Constraints

- Do not create real Google Ads, HubSpot, GA4, Search Console, Slack, or Monday credentials.
- Do not imply live platform access in capabilities or metadata.
- Keep `mvp_mode` or equivalent metadata set to `mock_only` until live integrations are explicitly approved.
- Do not rename these agent IDs once downstream work items use them.

## Future Registry Extensions

| Future field | Why it may be useful |
|---|---|
| `platform_scopes` | Tracks which systems an agent can read once live integrations exist |
| `approval_scope` | Distinguishes reviewer authority from final human approval |
| `cadence` | Supports weekly, monthly, or campaign-specific runs |
| `brand_scope` | Enables the same architecture to support brands beyond RISE |
| `evidence_requirements` | Defines minimum evidence before work can move to review |
