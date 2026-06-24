# MVP Marketing Loop PR Plan

## Implementation Status

The mock-only Clone Banks Marketing Agent Loop is implemented in `riseos-agent-orchestrator`.

The implemented loop is:

```text
manual mock request
-> Orchestrator creates a mock marketing workflow id
-> Orchestrator registers/seeds marketing agents in Agent Bus
-> Agent Bus receives specialist work items
-> canonical mock specialist evidence packets are created and attached
-> Hall marketing reviewer item is created
-> canonical Agent Bus review packet is created and attached when the deployed Agent Bus review lifecycle is available
-> rich mock risk_review artifact is created and attached
-> Clone Banks HQ synthesis item is created
-> rich mock synthesis_memo artifact is created and attached
-> Agent Bus Mission Control snapshot can show resulting agents, work items, and evidence references
```

The read-only Marketing Mission Control summary view is also implemented:

```text
GET /api/v1/marketing/workflows/{workflow_id}/summary
```

It joins Agent Bus work items and evidence packets by the mock workflow metadata created during the mock run, then displays the actual reviewer and HQ synthesis artifacts.

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
- reads `risk_review` and `synthesis_memo` artifact contents from actual attached evidence packets
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

## Agent Bus Evidence And Review Route Decision

Agent Bus already exposes canonical evidence lifecycle routes:

```text
POST /evidence-packets
POST /work-items/{work_item_id}/evidence
GET /evidence-packets/{evidence_id}
GET /work-items?repository=...
```

Agent Bus also defines canonical review lifecycle routes:

```text
POST /review-packets
POST /work-items/{work_item_id}/review
GET /review-packets/{review_id}
```

No Agent Bus code change was needed. The orchestrator Agent Bus client prefers the existing review routes for the reviewer lifecycle packet. If a deployed Agent Bus build does not have those routes fully installed, the mock run falls back to the rich `risk_review` evidence artifact and keeps the workflow safe and reviewable.

The richer governance payloads are stored in evidence packets with `artifact_type` / `evidence_type` values of `risk_review` and `synthesis_memo`.

## Live Integration Boundary

This MVP does not connect to live Google Ads, HubSpot, GA4, Search Console, Slack, Monday, Drive, OpenAI, or ChatGPT agents.

All evidence and governance artifacts are mock-only and explicitly marked with:

```json
{
  "mode": "mock_only",
  "confidence": "mock_only",
  "mock_only": true,
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
- four canonical mock specialist evidence packets are created and attached
- reviewer and Clone Banks HQ synthesis items are created
- one canonical Agent Bus review packet is created and attached when available
- `risk_review` and `synthesis_memo` artifacts are created and attached
- summary returns the expected structure for a mock workflow
- summary displays reviewer artifact fields from the actual packet
- summary displays HQ synthesis artifact fields from the actual packet
- missing workflow returns `404`
- Agent Bus unavailable returns a clean degraded error
- readiness flags become true when review and synthesis artifacts exist
- next action changes to human review once synthesis exists
- mock-only safeguards remain present

## Known Limitations

- This is a mock orchestration proof only; it does not execute specialist agents.
- Reviewer and HQ synthesis artifacts are generated by deterministic mock logic, not live agents.
- The Agent Bus review packet model stores lifecycle review fields; the richer marketing governance review content is attached as a `risk_review` evidence artifact.
- If the deployed Agent Bus review lifecycle route is unavailable, the canonical review packet id is omitted and the `risk_review` artifact remains the summary source of truth.
- Human approval readiness is visible in the summary, but durable human approval action is not yet implemented.
- Mission Control visibility depends on Agent Bus persistence and snapshot support.
- Orchestrator snapshot remains focused on orchestrator review/workflow state; Agent Bus Mission Control is the canonical view for Agent Bus work items and evidence.
- Repeated mock runs intentionally create additional mock records for MVP visibility.

## Recommended Next PR

Add the Marketing Agent Worker Adapter contract so real worker execution can eventually replace mock artifact generation while preserving these governance and approval boundaries.
