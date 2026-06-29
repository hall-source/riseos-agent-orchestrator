# Google Sheets / Drive Read-Only Evidence Adapter

## Why This Exists

The read-only fixture adapter proved that structured tabular evidence can replace one mock specialist packet without changing the governance chain.

This adapter adds the next contract boundary:

```text
read-only tabular source interface
-> normalize weekly marketing rows
-> create analytics_snapshot evidence
-> attach evidence to Hall Data Intelligence work item
-> summary reports google_sheets_readonly or drive_csv_readonly
```

## Endpoint

```http
POST /api/v1/marketing/evidence/google-sheets-readonly/attach
```

The endpoint is admin-protected and disabled unless:

```bash
ENABLE_MARKETING_SHEETS_READONLY_EVIDENCE=true
```

## Connector Status

The adapter interface is wired to an approved Google Sheets read-only source reader by default.

The default reader is intentionally narrow:

- supports only `source_type=google_sheet`
- reads only the requested `source_id`
- requires the source ID to be allowlisted
- requires an explicit sheet/tab name
- uses Google Sheets read-only scope
- never creates, edits, deletes, or writes Sheets or Drive files

Tests can still inject an in-memory source reader at:

```text
app.state.marketing_sheets_source_reader
```

That keeps the endpoint testable without live Google access.

## Required Environment

```bash
ENABLE_MARKETING_SHEETS_READONLY_EVIDENCE=true
MARKETING_READONLY_ALLOWED_SOURCE_IDS=approved_google_sheet_id
GOOGLE_APPLICATION_CREDENTIALS=/secure/path/to/service-account.json
```

`MARKETING_READONLY_ALLOWED_SOURCE_IDS` is a comma-separated allowlist. The endpoint rejects any source ID that is not present in that list.

`GOOGLE_APPLICATION_CREDENTIALS` must point to a deployment-provided service account JSON file. Do not commit credentials and do not log credential contents.

## Required Google Permission

The reader requests only:

```text
https://www.googleapis.com/auth/spreadsheets.readonly
```

Do not grant write scopes. Do not grant broad Drive scopes for this path.

## Supported Mapping

Only one agent/evidence mapping is supported:

```text
hall-data-intelligence -> analytics_snapshot
```

The adapter refuses PPC, SEO, creative, HubSpot, Google Ads, GA4, Search Console, Slack, Monday, OpenAI, and ChatGPT agent paths.

## Approved Sheet Schema

The first approved Google Sheet tab is expected to be named:

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

## Request Shape

```json
{
  "workflow_id": "...",
  "agent_id": "hall-data-intelligence",
  "work_item_id": "...",
  "source_type": "google_sheet",
  "source_id": "...",
  "sheet_name": "Weekly Marketing Snapshot",
  "date_range_label": "last_7_days",
  "mapping": {
    "leads": "leads",
    "contacts_created": "contacts_created",
    "deals_created": "deals_created",
    "sessions": "sessions",
    "source": "source"
  }
}
```

The request model still accepts `drive_csv` for the interface contract, but the default approved reader added after the interface PR only supports `google_sheet`. A Drive CSV reader would need a separate, explicit implementation and review.

## Source Reader Interface

The adapter depends on a read-only row reader interface:

```text
MarketingReadOnlyTabularSourceReader.read_rows(payload) -> list[dict]
```

The production default is `ApprovedGoogleSheetsReadOnlySourceReader`. Tests may inject an alternate reader at:

```text
app.state.marketing_sheets_source_reader
```

## Failure Behavior

The approved reader fails closed when:

- credentials are missing
- credentials cannot be refreshed
- source ID is missing
- source ID is not allowlisted
- sheet name is missing
- expected columns are missing
- no rows match `date_range_label`
- Google Sheets returns an error or invalid response

## Evidence Packet

For Google Sheets, the evidence packet includes:

```json
{
  "evidence_type": "analytics_snapshot",
  "produced_by": "hall-data-intelligence",
  "workflow_id": "...",
  "source_mode": "google_sheets_readonly",
  "summary": "Read-only Google Sheets snapshot converted into analytics evidence.",
  "date_range_label": "last_7_days",
  "metrics": {
    "leads": 42,
    "contacts_created": 38,
    "deals_created": 6,
    "sessions": 1200,
    "deal_created_rate_from_leads": 0.1429
  },
  "source_breakdown": [],
  "findings": [],
  "confidence": "read_only_source",
  "mode": "mock_only",
  "live_platform_access": false,
  "write_access": false,
  "not_for_real_marketing_decisions": true,
  "approval_required": false
}
```

`mode=mock_only` keeps the existing mock governance safety check intact. `source_mode=google_sheets_readonly` is the summary-visible source classification.

## Normalization

The adapter:

- reads rows through the configured read-only source reader
- filters rows by `date_range_label`
- maps configured columns into `leads`, `contacts_created`, `deals_created`, `sessions`, and `source`
- totals numeric metrics across matching rows
- calculates `deal_created_rate_from_leads`
- groups rows into `source_breakdown`
- rejects invalid or negative numeric values

## Summary Behavior

The workflow summary counts source modes from evidence packets. After this adapter attaches evidence, summary can show:

```json
{
  "evidence_source_modes": {
    "mock_generated": 3,
    "read_only_fixture": 1,
    "google_sheets_readonly": 1
  }
}
```

## Safety Guarantees

This adapter does not:

- connect Google Ads, HubSpot, GA4, Search Console, Slack, Monday, OpenAI, or ChatGPT agents
- perform write actions
- create, edit, or delete Drive files
- modify Sheets
- authorize real business decisions

Every evidence packet includes:

```json
{
  "live_platform_access": false,
  "write_access": false,
  "not_for_real_marketing_decisions": true,
  "approval_required": false
}
```

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

Run governance and approval:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/governance/mock/run-once \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"workflow_id":"'$WORKFLOW_ID'","run_reviewer":true,"run_hq_synthesis":true}' | jq .

curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/workflows/$WORKFLOW_ID/approval \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "decision":"approve_mock",
    "approved_by":"Hall",
    "notes":"Google Sheets read-only evidence path reviewed. No production action authorized."
  }' | jq .
```

Read summary:

```bash
curl -sS http://127.0.0.1:8055/api/v1/marketing/workflows/$WORKFLOW_ID/summary \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" | jq .
```

## Remaining Before Broader Live Connector Use

Before this path expands beyond one approved source, the system still needs:

- deployment configuration for the approved source ID and service account file
- audit review of the exact service account permissions
- timeout, retry, and rate-limit tuning after first runtime validation
- a separate PR for any Drive CSV reader
- a separate approval gate before any real marketing decision can use the evidence
