# Approved Read-Only Source Reader

## Purpose

This document describes the first approved live read-only source reader for the marketing evidence path.

The reader is intentionally narrow:

```text
one allowlisted Google Sheet
-> one explicit tab
-> one weekly marketing snapshot schema
-> hall-data-intelligence analytics_snapshot evidence
```

It does not create a broad Google connector, Drive crawler, file search tool, or write-capable integration.

## Endpoint

The reader is used by the existing endpoint:

```http
POST /api/v1/marketing/evidence/google-sheets-readonly/attach
```

The endpoint remains admin-protected and feature-flagged.

## Required Environment

```bash
ENABLE_MARKETING_SHEETS_READONLY_EVIDENCE=true
MARKETING_READONLY_ALLOWED_SOURCE_IDS=approved_google_sheet_id
GOOGLE_APPLICATION_CREDENTIALS=/secure/path/to/service-account.json
```

`MARKETING_READONLY_ALLOWED_SOURCE_IDS` is a comma-separated list. Only source IDs in that list are accepted.

`GOOGLE_APPLICATION_CREDENTIALS` must point to a deployment-provided service account JSON file. Never commit credentials. Never print credential contents.

## Google Scope

The reader requests exactly this scope:

```text
https://www.googleapis.com/auth/spreadsheets.readonly
```

Do not add Sheets write scopes. Do not add broad Drive scopes. Do not grant this service account access to unrelated Sheets.

## Approved Sheet Schema

The approved source should expose a tab named:

```text
Weekly Marketing Snapshot
```

Expected columns:

```text
date_range_label
source
leads
contacts_created
deals_created
sessions
```

Example rows:

```text
last_7_days | paid_search    | 18 | 16 | 3 | 450
last_7_days | organic_search | 14 | 12 | 2 | 500
last_7_days | direct         | 10 | 10 | 1 | 250
```

Rows are filtered by the request `date_range_label`. Only matching rows are converted to evidence.

## Failure Behavior

The reader fails closed when:

- `ENABLE_MARKETING_SHEETS_READONLY_EVIDENCE` is false
- admin auth is missing
- `source_id` is missing
- `source_id` is not in `MARKETING_READONLY_ALLOWED_SOURCE_IDS`
- `sheet_name` is missing
- `GOOGLE_APPLICATION_CREDENTIALS` is missing
- the credential file is not readable
- credentials cannot refresh
- Google Sheets returns an error
- the sheet response has no tabular values
- expected columns are missing
- no rows match `date_range_label`
- numeric metric fields are invalid or negative

## Evidence Output

The evidence packet uses:

```json
{
  "evidence_type": "analytics_snapshot",
  "produced_by": "hall-data-intelligence",
  "source_mode": "google_sheets_readonly",
  "confidence": "read_only_source",
  "live_platform_access": false,
  "write_access": false,
  "not_for_real_marketing_decisions": true,
  "approval_required": false
}
```

The packet also includes normalized metrics, source breakdown, and `deal_created_rate_from_leads`.

## Safety Guarantees

This reader does not:

- write to Google Sheets
- create, edit, delete, or search Drive files
- call Google Ads, HubSpot, GA4, Search Console, Slack, Monday, OpenAI, or ChatGPT agents
- approve production marketing actions
- authorize real business decisions

## Validation Flow

Create workflow:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/weekly-command-brief/mock-run \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "business_unit":"RISE Commercial District",
    "requested_by":"Hall",
    "date_range_label":"last_7_days",
    "auto_complete_specialists": false
  }' | jq .
```

Attach Google Sheets read-only evidence:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/evidence/google-sheets-readonly/attach \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "'$WORKFLOW_ID'",
    "agent_id": "hall-data-intelligence",
    "work_item_id": "'$DATA_WORK_ITEM_ID'",
    "source_type": "google_sheet",
    "source_id": "'$MARKETING_TEST_SHEET_ID'",
    "sheet_name": "Weekly Marketing Snapshot",
    "date_range_label": "last_7_days"
  }' | jq .
```

Run remaining mock workers:

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

Approve mock workflow:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/workflows/$WORKFLOW_ID/approval \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "approve_mock",
    "approved_by": "Hall",
    "notes": "Google Sheets read-only evidence path reviewed. No production action authorized."
  }' | jq .
```

Read summary:

```bash
curl -sS http://127.0.0.1:8055/api/v1/marketing/workflows/$WORKFLOW_ID/summary \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" | jq .
```

Confirm:

```json
{
  "evidence_source_modes": {
    "google_sheets_readonly": 1
  }
}
```

## What Is Not Connected Yet

- Drive CSV read access
- Drive file search or crawling
- Google Ads
- HubSpot
- GA4
- Search Console
- Slack writes
- Monday writes
- OpenAI calls
- ChatGPT agent calls
- production marketing actions
