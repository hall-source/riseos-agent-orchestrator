# MVP Marketing Loop PR Plan

## Implementation Status

This PR implements the first mock-only Clone Banks Marketing Agent Loop in `riseos-agent-orchestrator`.

The implemented loop is:

```text
manual mock request
-> Orchestrator creates a mock marketing workflow id
-> Orchestrator registers/seeds marketing agents in Agent Bus
-> Agent Bus receives specialist work items
-> canonical mock evidence packets are created and attached
-> Hall marketing reviewer item is created
-> Clone Banks HQ synthesis item is created
-> Agent Bus Mission Control snapshot can show resulting agents, work items, and evidence references
```

## Endpoint

```http
POST /api/v1/marketing/weekly-command-brief/mock-run
```

The endpoint is admin-protected. It accepts the existing orchestrator admin header:

```text
X-Orchestrator-Admin-Token: $ORCHESTRATOR_ADMIN_TOKEN
```

It also accepts the requested bearer-token form:

```text
Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN
```

## Mock Metadata

The mock run uses this metadata convention:

```json
{
  "domain": "marketing",
  "brand": "rise",
  "business_unit": "RISE Commercial District",
  "workflow_type": "weekly_marketing_command_brief",
  "source_event": "manual_mock_request",
  "approval_required": true,
  "human_owner": "Hall",
  "review_agent": "hall-marketing-reviewer"
}
```

Runtime metadata also includes `mvp_mode=mock_only` and `live_platform_access=false`.

## Required Agents

```text
clone-banks-hq
hall-data-intelligence
hall-ppc-intelligence
hall-seo-intelligence
hall-creative-strategist
hall-marketing-reviewer
```

## Agent Bus Evidence Route Decision

Agent Bus already exposes canonical evidence lifecycle routes:

```text
POST /evidence-packets
POST /work-items/{work_item_id}/evidence
```

No Agent Bus code change was needed for this PR. The orchestrator Agent Bus client now wraps these existing routes and uses them for mock evidence creation and attachment.

## Live Integration Boundary

This MVP does not connect to live Google Ads, HubSpot, GA4, Search Console, Slack, Monday, Drive, OpenAI, or ChatGPT agents.

All evidence is mock-only and explicitly marked with:

```json
{
  "mode": "mock_only",
  "confidence": "mock_only",
  "live_platform_access": false
}
```

## Local And Vultr Validation Commands

Health checks using target Vultr ports:

```bash
curl -sS http://127.0.0.1:8050/health
curl -sS http://127.0.0.1:8055/health
```

Example endpoint call:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/weekly-command-brief/mock-run \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "business_unit": "RISE Commercial District",
    "requested_by": "Hall",
    "date_range_label": "mock_last_7_days"
  }' | jq .
```

Verify Agent Bus state:

```bash
curl -sS http://127.0.0.1:8050/api/v1/mission-control/snapshot | jq .
```

Verify Orchestrator state:

```bash
curl -sS http://127.0.0.1:8055/api/v1/orchestrator/snapshot | jq .
```

## Test Plan

```bash
pytest tests/test_marketing_loop.py
pytest
```

The focused tests use a fake Agent Bus client and verify:

- missing admin token is rejected
- bearer-token admin auth is accepted
- existing `X-Orchestrator-Admin-Token` auth still works
- all six marketing agents are seeded
- four specialist work items are created
- four canonical mock evidence packets are created and attached
- reviewer and Clone Banks HQ synthesis items are created
- no live platform access is represented in metadata

## Known Limitations

- This is a mock orchestration proof only; it does not execute specialist agents.
- The reviewer and HQ synthesis items are queued work items, not real agent outputs.
- Mission Control visibility depends on Agent Bus persistence and snapshot support.
- Orchestrator snapshot remains focused on orchestrator review/workflow state; Agent Bus Mission Control is the canonical view for Agent Bus work items and evidence.
- Repeated mock runs intentionally create additional mock records for MVP visibility.

## Recommended Next PR

Add a read-only marketing workflow summary view that joins the orchestrator mock workflow id with Agent Bus work items, evidence packet IDs, reviewer item, and HQ synthesis item so Mission Control can display a clean weekly command brief run card.
