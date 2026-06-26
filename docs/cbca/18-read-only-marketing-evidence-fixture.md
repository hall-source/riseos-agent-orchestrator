# Read-Only Marketing Evidence Fixture Adapter

## Why This Exists

The marketing loop has deterministic mock evidence, worker execution, governance artifacts, and mock human approval.

This adapter adds the first safe bridge toward structured read-only evidence without connecting any live platform:

```text
weekly fixture payload
-> validate Hall Data Intelligence work item
-> derive simple metrics
-> attach analytics_snapshot evidence
-> summary reports read_only_fixture source mode
```

## Endpoint

```http
POST /api/v1/marketing/evidence/read-only-fixture/attach
```

The endpoint is admin-protected and disabled unless:

```bash
ENABLE_MARKETING_READONLY_EVIDENCE=true
```

## Supported Mapping

Only one mapping is supported in this first contract:

```text
hall-data-intelligence -> analytics_snapshot
```

The adapter refuses other agents and refuses work items where `live_platform_access` is not `false`.

## Request Shape

```json
{
  "work_item_id": "...",
  "workflow_id": "marketing-wf-...",
  "fixture": {
    "business_unit": "RISE Commercial District",
    "date_range_label": "fixture_last_7_days",
    "website_sessions": 1000,
    "leads": 100,
    "qualified_leads": 40,
    "deals_created": 10,
    "pipeline_value": 25000,
    "closed_won_value": 5000,
    "notes": "Fixture-only weekly marketing snapshot."
  }
}
```

`workflow_id` is optional but recommended. When supplied, it must match the work item metadata.

## Derived Metrics

The adapter calculates:

| Metric | Formula |
|---|---|
| `lead_conversion_rate` | `leads / website_sessions` |
| `qualified_lead_rate` | `qualified_leads / leads` |
| `deal_created_rate` | `deals_created / leads` |
| `deal_created_per_session_rate` | `deals_created / website_sessions` |

Rates return `0.0` when the denominator is zero.

## Evidence Packet

The adapter creates an Agent Bus evidence packet with:

```json
{
  "evidence_type": "analytics_snapshot",
  "artifact_type": "analytics_snapshot",
  "produced_by": "hall-data-intelligence",
  "source_mode": "read_only_fixture",
  "source_label": "weekly_marketing_snapshot_fixture",
  "mode": "mock_only",
  "fixture": {},
  "derived_metrics": {},
  "confidence": "fixture_only",
  "live_platform_access": false,
  "write_access": false,
  "not_for_real_marketing_decisions": true,
  "approval_required": false
}
```

`mode=mock_only` keeps the existing governance safety check intact. `source_mode=read_only_fixture` is the summary-visible source classification.

## Summary Behavior

The workflow summary now includes evidence source-mode counts:

```json
{
  "evidence_source_modes": {
    "mock_generated": 3,
    "read_only_fixture": 1
  }
}
```

Evidence packets with `source_mode=read_only_fixture` count as fixture evidence. Existing mock packets without a source mode but with `mode=mock_only` or `confidence=mock_only` count as `mock_generated`.

## Safety Boundaries

This adapter does not:

- connect Google Ads, HubSpot, GA4, Search Console, Slack, Monday, Drive, or any production system
- call OpenAI
- call ChatGPT agents
- execute real agents
- write to any external marketing platform
- approve production action

Every attached fixture evidence packet includes:

```json
{
  "source_mode": "read_only_fixture",
  "mode": "mock_only",
  "live_platform_access": false,
  "write_access": false,
  "not_for_real_marketing_decisions": true
}
```

## Validation Flow

Create a workflow without auto-completing specialists:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/weekly-command-brief/mock-run \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "business_unit":"RISE Commercial District",
    "requested_by":"Hall",
    "date_range_label":"mock_last_7_days",
    "auto_complete_specialists": false
  }' | jq .
```

Attach fixture evidence to the Hall Data Intelligence work item:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/evidence/read-only-fixture/attach \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "work_item_id":"'$HALL_DATA_WORK_ITEM_ID'",
    "workflow_id":"'$WORKFLOW_ID'",
    "fixture": {
      "business_unit":"RISE Commercial District",
      "date_range_label":"fixture_last_7_days",
      "website_sessions":1000,
      "leads":100,
      "qualified_leads":40,
      "deals_created":10,
      "pipeline_value":25000,
      "closed_won_value":5000
    }
  }' | jq .
```

Run remaining mock specialists:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/workers/mock/run-once \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id":"'$WORKFLOW_ID'",
    "max_items":4
  }' | jq .
```

Run governance and approval as usual:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/governance/mock/run-once \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"workflow_id":"'$WORKFLOW_ID'","run_reviewer":true,"run_hq_synthesis":true}' | jq .

curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/workflows/$WORKFLOW_ID/approval \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"decision":"approve_mock","approved_by":"Hall","notes":"Read-only fixture evidence reviewed."}' | jq .
```

Confirm summary shows fixture evidence:

```bash
curl -sS http://127.0.0.1:8055/api/v1/marketing/workflows/$WORKFLOW_ID/summary \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" | jq '.evidence_source_modes'
```

## Remaining Before Live Read-Only Evidence

Before replacing fixtures with real read-only platform evidence, the system still needs:

- per-platform read-only credential handling
- source-specific audit logs
- no-write integration tests
- rate limit and timeout behavior
- clear labeling of live read-only source modes
- approval boundaries for recommendations based on real data
