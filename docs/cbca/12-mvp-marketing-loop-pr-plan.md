# MVP Marketing Loop PR Plan

## Implementation Status

The mock-only Clone Banks Marketing Agent Loop is implemented in `riseos-agent-orchestrator`.

The current staged validation path is:

```text
manual mock request with auto_complete_specialists=false
-> Orchestrator creates specialist, reviewer, and HQ work items
-> optional Hall Data Intelligence read-only fixture evidence is attached
-> Marketing Worker Adapter claims remaining specialist work
-> Marketing Worker Adapter attaches deterministic mock evidence
-> Governance Stage Runner validates specialist evidence exists
-> Governance Stage Runner creates hall-marketing-reviewer risk_review
-> Governance Stage Runner creates clone-banks-hq synthesis_memo
-> summary shows human approval ready
-> Hall or Marcus records approve/reject/request-changes
-> summary shows the durable mock approval decision
```

The default mock loop can still auto-complete specialist evidence for backwards compatibility.

## Endpoints

### Mock Run

```http
POST /api/v1/marketing/weekly-command-brief/mock-run
```

Set `auto_complete_specialists=false` when validating worker, fixture, governance, and approval stages separately.

### Worker Run Once

```http
POST /api/v1/marketing/workers/mock/run-once
```

Requires:

```bash
ENABLE_MARKETING_WORKER_MOCK=true
```

### Read-Only Fixture Evidence

```http
POST /api/v1/marketing/evidence/read-only-fixture/attach
```

Requires:

```bash
ENABLE_MARKETING_READONLY_EVIDENCE=true
```

Only this first mapping is supported:

```text
hall-data-intelligence -> analytics_snapshot
```

The endpoint accepts a weekly marketing snapshot fixture, calculates simple derived rates, creates an `analytics_snapshot` evidence packet, and attaches it to the provided Hall Data Intelligence work item.

### Governance Run Once

```http
POST /api/v1/marketing/governance/mock/run-once
```

Requires:

```bash
ENABLE_MARKETING_GOVERNANCE_MOCK=true
```

It creates the `risk_review` and `synthesis_memo` artifacts after specialist evidence exists.

### Mock Approval

```http
POST /api/v1/marketing/workflows/{workflow_id}/approval
GET /api/v1/marketing/workflows/{workflow_id}/approval
```

POST requires:

```bash
ENABLE_MARKETING_APPROVAL_MOCK=true
```

Supported decisions:

```text
approve_mock
reject_mock
request_changes
```

### Summary

```http
GET /api/v1/marketing/workflows/{workflow_id}/summary
```

The summary endpoint reads Agent Bus work items and evidence packets, then reports:

- specialist evidence status
- reviewer `risk_review`
- HQ `synthesis_memo`
- human approval state
- readiness flags
- next action
- evidence source-mode counts, including `mock_generated` and `read_only_fixture`

## Agent Bus Evidence Decision

Agent Bus evidence packets remain the durable carrier for rich marketing artifacts:

```text
analytics_snapshot
risk_review
synthesis_memo
human_approval
```

No Agent Bus code change is required for the fixture adapter contract.

## Safety Boundary

This MVP does not connect to live Google Ads, HubSpot, GA4, Search Console, Slack, Monday, Drive, OpenAI, or ChatGPT agents.

Read-only fixture evidence is not live data. Every fixture packet includes:

```json
{
  "source_mode": "read_only_fixture",
  "live_platform_access": false,
  "write_access": false,
  "not_for_real_marketing_decisions": true
}
```

Mock-generated packets continue to be counted as `mock_generated` in the summary.

## Validation Flow

Create a workflow without auto-completing specialists:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/weekly-command-brief/mock-run \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "business_unit": "RISE Commercial District",
    "requested_by": "Hall",
    "date_range_label": "mock_last_7_days",
    "auto_complete_specialists": false
  }' | jq .
```

Attach read-only fixture evidence to the Hall Data Intelligence work item:

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
  -d '{"workflow_id":"'$WORKFLOW_ID'","max_items":4}' | jq .
```

Run governance:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/governance/mock/run-once \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"workflow_id":"'$WORKFLOW_ID'","run_reviewer":true,"run_hq_synthesis":true}' | jq .
```

Approve mock synthesis:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/workflows/$WORKFLOW_ID/approval \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"decision":"approve_mock","approved_by":"Hall","notes":"Read-only fixture evidence reviewed."}' | jq .
```

Confirm summary source modes:

```bash
curl -sS http://127.0.0.1:8055/api/v1/marketing/workflows/$WORKFLOW_ID/summary \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" | jq '.evidence_source_modes'
```

Verify Agent Bus state:

```bash
curl -sS http://127.0.0.1:8050/api/v1/mission-control/snapshot | jq .
```

## Test Plan

```bash
pytest tests/test_marketing_readonly_evidence.py
pytest tests/test_marketing_governance.py
pytest tests/test_marketing_worker.py
pytest tests/test_marketing_loop.py
pytest
```

## Known Limitations

- Fixture evidence is structured but not live data.
- Only `hall-data-intelligence -> analytics_snapshot` is supported.
- The fixture adapter is not a daemon and does not execute real agents.
- No production action is triggered by fixture evidence, governance, or approval.
- Repeated mock runs intentionally create additional mock records for MVP visibility.

## Recommended Next PR

Add the first real read-only source adapter behind a strict safe flag, starting with one source and no write capability.
