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

This PR adds the adapter interface and safe local test double. It does not wire live Google Sheets or Drive credentials in this repo.

If no source reader is configured on the app, the endpoint fails closed with:

```text
No Google Sheets or Drive CSV read-only source reader is configured for this environment.
```

That is intentional. The PR should not pretend live Google Sheets access exists when the connector is not installed.

## Supported Mapping

Only one agent/evidence mapping is supported:

```text
hall-data-intelligence -> analytics_snapshot
```

The adapter refuses PPC, SEO, creative, HubSpot, Google Ads, GA4, Search Console, Slack, Monday, OpenAI, and ChatGPT agent paths.

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

`source_type` may be:

```text
google_sheet
drive_csv
```

`drive_csv` uses the same row normalization path and emits `source_mode=drive_csv_readonly`.

## Source Reader Interface

The adapter depends on a read-only row reader interface:

```text
MarketingReadOnlyTabularSourceReader.read_rows(payload) -> list[dict]
```

The endpoint looks for a configured reader at:

```text
app.state.marketing_sheets_source_reader
```

Tests provide a local in-memory reader. A future PR can replace that with an actual Google Sheets or Drive CSV reader without changing the evidence contract.

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

`mode=mock_only` keeps the existing mock governance safety check intact. `source_mode=google_sheets_readonly` or `drive_csv_readonly` is the summary-visible source classification.

## Normalization

The adapter:

- reads rows through the configured read-only source reader
- maps configured columns into `leads`, `contacts_created`, `deals_created`, `sessions`, and `source`
- totals numeric metrics across rows
- calculates `deal_created_rate_from_leads`
- groups rows into `source_breakdown`
- rejects invalid or negative numeric values

## Summary Behavior

The workflow summary already counts source modes from evidence packets. After this adapter attaches evidence, summary can show:

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
    "source_id": "SAFE_TEST_SOURCE_ID",
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

## Remaining Before Live Connector Use

Before live Google Sheets or Drive CSV reads can run outside tests, the system still needs:

- a configured read-only Google/Drive source reader
- credential handling with read-only scopes only
- source allowlist or safe source registry
- audit logging for each read
- timeout, retry, and rate-limit behavior
- tests proving no write scopes or write methods are used
