# MVP Marketing Loop PR Plan

## Implementation Status

The mock-only Clone Banks Marketing Agent Loop is implemented in `riseos-agent-orchestrator`.

The current staged validation path is:

```text
manual mock request with auto_complete_specialists=false
-> Orchestrator creates specialist, reviewer, and HQ work items
-> optional Hall Data Intelligence read-only fixture evidence is attached
-> optional Hall Data Intelligence Google Sheets / Drive CSV read-only evidence is attached
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

Set `auto_complete_specialists=false` when validating worker, fixture, read-only source, governance, and approval stages separately.

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

### Google Sheets / Drive Read-Only Evidence

```http
POST /api/v1/marketing/evidence/google-sheets-readonly/attach
```

Requires:

```bash
ENABLE_MARKETING_SHEETS_READONLY_EVIDENCE=true
```

Only this first mapping is supported:

```text
hall-data-intelligence -> analytics_snapshot
```

The endpoint validates a read-only source descriptor, reads tabular rows through a configured source reader, normalizes the weekly marketing snapshot fields, calculates simple derived rates, creates an `analytics_snapshot` evidence packet, and attaches it to the provided Hall Data Intelligence work item.

The PR adds the adapter interface and local test double. It does not wire a live Google Sheets or Drive connector by default. If no read-only source reader is configured, the endpoint fails closed with a clear source-read error.

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
- evidence source-mode counts, including `mock_generated`, `read_only_fixture`, `google_sheets_readonly`, and `drive_csv_readonly` when those packets exist

## Agent Bus Evidence Decision

Agent Bus evidence packets remain the durable carrier for rich marketing artifacts:

```text
analytics_snapshot
risk_review
synthesis_memo
human_approval
```

No Agent Bus code change is required for the fixture adapter or Sheets/Drive adapter contract.

## Safety Boundary

This MVP does not connect to live Google Ads, HubSpot, GA4, Search Console, Slack, Monday, OpenAI, or ChatGPT agents.

Read-only fixture evidence is not live data. Every fixture packet includes:

```json
{
  "source_mode": "read_only_fixture",
  "live_platform_access": false,
  "write_access": false,
  "not_for_real_marketing_decisions": true
}
```

Google Sheets / Drive read-only evidence uses the same no-write contract. Every packet includes:

```json
{
  "source_mode": "google_sheets_readonly",
  "confidence": "read_only_source",
  "live_platform_access": false,
  "write_access": false,
  "not_for_real_marketing_decisions": true,
  "approval_required": false
}
```

The adapter interface can later be connected to a safe read-only source reader, but this PR does not create, edit, delete, or write any Google Sheet or Drive file.

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
    "date_range_label": "last_7_days",
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

Or attach Google Sheets / Drive CSV read-only evidence through a configured read-only source reader:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/evidence/google-sheets-readonly/attach \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id":"'$WORKFLOW_ID'",
    "agent_id":"hall-data-intelligence",
    "work_item_id":"'$HALL_DATA_WORK_ITEM_ID'",
    "source_type":"google_sheet",
    "source_id":"SAFE_TEST_SOURCE_ID",
    "sheet_name":"Weekly Marketing Snapshot",
    "date_range_label":"last_7_days"
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
  -d '{"decision":"approve_mock","approved_by":"Hall","notes":"Read-only evidence reviewed. No production action authorized."}' | jq .
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
pytest tests/test_marketing_sheets_evidence.py
pytest tests/test_marketing_readonly_evidence.py
pytest tests/test_marketing_approval.py
pytest tests/test_marketing_governance.py
pytest tests/test_marketing_worker.py
pytest tests/test_marketing_loop.py
pytest
```

## Known Limitations

- Fixture evidence is structured but not live data.
- The Sheets/Drive adapter adds the source-reader interface and local test double, but no live Google connector is configured by default.
- Only `hall-data-intelligence -> analytics_snapshot` is supported for fixture and Sheets/Drive evidence.
- The read-only adapters are not daemons and do not execute real agents.
- No production action is triggered by read-only evidence, governance, or approval.
- Repeated mock runs intentionally create additional mock records for MVP visibility.

## Recommended Next PR

Wire a deployment-specific read-only Google Sheets or Drive CSV reader behind least-privilege credentials, then validate that the endpoint can read one approved source without granting write scopes.
