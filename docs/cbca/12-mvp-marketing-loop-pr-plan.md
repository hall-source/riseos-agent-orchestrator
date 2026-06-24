# MVP Marketing Loop PR Plan

## Implementation Status

The first mock-only Clone Banks Marketing Agent Loop is implemented in `riseos-agent-orchestrator`.

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

The follow-up read-only Marketing Mission Control summary view is also implemented:

```text
GET /api/v1/marketing/workflows/{workflow_id}/summary
```

It joins Agent Bus work items and evidence packets by the mock workflow metadata created during the mock run.

## Mock Run Endpoint

```http
POST /api/v1/marketing/weekly-command-brief/mock-run
```

The endpoint is admin-protected. It accepts the existing orchestrator admin header:

```text
X-Orchestrator-Admin-Token: $ORCHESTRATOR_ADMIN_TOKEN
```

It also accepts the bearer-token form:

```text
Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN
```

## Summary Endpoint

```http
GET /api/v1/marketing/workflows/{workflow_id}/summary
```

The endpoint is read-only and admin-protected with the same auth patterns as the mock-run endpoint. It does not create, update, or execute work items.

The summary endpoint:

- accepts a `workflow_id`
- lists Agent Bus work items for `hall-source/riseos-agent-orchestrator`
- filters work items where `metadata.workflow_id` matches the requested workflow
- fetches attached evidence packets from `metadata.evidence_packet_ids`
- groups specialists, reviewer, and Clone Banks HQ synthesis items
- computes readiness flags, missing packets, workflow status, and a plain-English next action
- returns `404` when no matching workflow work items exist
- returns a clean degraded error when Agent Bus is unavailable

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
GET /evidence-packets/{evidence_id}
GET /work-items?repository=...
```

No Agent Bus code change was needed. The orchestrator Agent Bus client wraps these existing routes for mock evidence creation, attachment, and read-only summary generation.

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

Create a mock run:

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

Then read the summary:

```bash
curl -sS http://127.0.0.1:8055/api/v1/marketing/workflows/$WORKFLOW_ID/summary \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" | jq .
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
- summary returns the expected structure for a mock workflow
- missing workflow returns `404`
- Agent Bus unavailable returns a clean degraded error
- readiness flags and next action change as review, synthesis, and human approval are represented
- no live platform access is represented in metadata

## Known Limitations

- This is a mock orchestration proof only; it does not execute specialist agents.
- The reviewer and HQ synthesis items are queued work items, not real agent outputs.
- The summary endpoint infers review, synthesis, and human approval completion from work-item status and metadata because no real reviewer or HQ output is produced yet.
- Mission Control visibility depends on Agent Bus persistence and snapshot support.
- Orchestrator snapshot remains focused on orchestrator review/workflow state; Agent Bus Mission Control is the canonical view for Agent Bus work items and evidence.
- Repeated mock runs intentionally create additional mock records for MVP visibility.

## Recommended Next PR

Add canonical mock review and HQ synthesis packet creation so the summary endpoint can stop relying on inferred metadata for reviewer/HQ completion and can display richer Marketing Mission Control outputs.
