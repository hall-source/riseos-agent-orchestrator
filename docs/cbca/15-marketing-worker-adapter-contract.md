# Marketing Worker Adapter Contract

## Why This Exists

The mock Weekly Marketing Command Brief originally let the orchestrator create the entire workflow, including specialist evidence, reviewer artifacts, and Clone Banks HQ synthesis artifacts.

That proved the governance loop, but it did not prove the worker boundary.

The worker adapter introduces the first safe bridge between Agent Bus work items and future specialist execution:

```text
Orchestrator creates marketing work items
-> Worker Adapter claims eligible specialist work
-> Worker Adapter runs deterministic mock specialist logic
-> Worker Adapter attaches structured evidence
-> Reviewer/HQ governance remains separate
```

## What It Does

The first adapter is callable from tests and from an admin-protected run-once endpoint:

```http
POST /api/v1/marketing/workers/mock/run-once
```

It can:

- poll Agent Bus for `hall-source/riseos-agent-orchestrator` work items
- filter to mock-only Weekly Marketing Command Brief specialist work
- claim eligible work for the assigned specialist agent
- mark work `in_progress` when the current Agent Bus lifecycle supports it
- run a deterministic mock specialist runner
- create and attach an evidence packet
- complete the work item, or transition toward review if completion is not supported
- return a structured worker result

## What It Does Not Do Yet

The adapter does not:

- connect live Google Ads, HubSpot, GA4, Search Console, Slack, Monday, or Drive
- call OpenAI
- call ChatGPT agents
- execute real specialist agents
- write to live marketing platforms
- approve production actions
- run as a daemon or background service

## Worker Input Contract

The run-once endpoint accepts:

```json
{
  "workflow_id": "marketing-wf-...",
  "max_items": 4
}
```

`workflow_id` is optional for the function contract, but callers should pass it during validation to keep one run scoped to one mock workflow.

Eligible Agent Bus work items must be mock-only specialist work. The worker accepts both the new worker role convention and the previous mock-loop role for compatibility:

```json
{
  "domain": "marketing",
  "workflow_type": "weekly_marketing_command_brief",
  "work_item_role": "specialist",
  "mock_mode": true,
  "live_platform_access": false
}
```

The current mock-loop work items also include:

```json
{
  "work_item_role": "specialist_evidence",
  "worker_role": "specialist",
  "mvp_mode": "mock_only"
}
```

## Worker Output Contract

Each processed item returns:

```json
{
  "worker_run_id": "marketing-worker-run-...",
  "workflow_id": "marketing-wf-...",
  "agent_id": "hall-ppc-intelligence",
  "work_item_id": "...",
  "status": "completed",
  "evidence_packet_id": "...",
  "mock_mode": true,
  "live_platform_access": false,
  "next_action": "ready_for_review"
}
```

The endpoint wraps item results:

```json
{
  "worker_run_id": "marketing-worker-run-...",
  "workflow_id": "marketing-wf-...",
  "processed": 4,
  "results": []
}
```

## Agent Registry Contract

`app/marketing_agent_registry.py` defines the current marketing agent registry.

Each entry includes:

- `agent_id`
- `display_name`
- `agent_type`
- `capabilities`
- `default_work_item_roles`
- `allowed_evidence_types`
- `live_integrations_enabled=false`

Current agents:

```text
clone-banks-hq
hall-data-intelligence
hall-ppc-intelligence
hall-seo-intelligence
hall-creative-strategist
hall-marketing-reviewer
```

The registry is for routing and validation only. It does not call live agents.

## Mock Runner Behavior

The adapter has deterministic mock runners for:

| Agent | Evidence type |
|---|---|
| `hall-data-intelligence` | `analytics_snapshot` |
| `hall-ppc-intelligence` | `ppc_snapshot` |
| `hall-seo-intelligence` | `seo_performance_snapshot` |
| `hall-creative-strategist` | `creative_strategy_brief` |

Every evidence packet includes:

```json
{
  "mode": "mock_only",
  "confidence": "mock_only",
  "mock_mode": true,
  "live_platform_access": false,
  "approval_required": false,
  "not_for_real_marketing_decisions": true
}
```

## Safety Flag

The endpoint is disabled unless this environment variable is set:

```bash
ENABLE_MARKETING_WORKER_MOCK=true
```

Admin auth is still required:

```text
Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN
```

or:

```text
X-Orchestrator-Admin-Token: $ORCHESTRATOR_ADMIN_TOKEN
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

Run one worker pass:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/workers/mock/run-once \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id":"'$WORKFLOW_ID'",
    "max_items":4
  }' | jq .
```

Read the summary:

```bash
curl -sS http://127.0.0.1:8055/api/v1/marketing/workflows/$WORKFLOW_ID/summary \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" | jq .
```

Verify Agent Bus:

```bash
curl -sS http://127.0.0.1:8050/api/v1/mission-control/snapshot | jq .
```

## Future Live-Agent Options

Future PRs can replace the deterministic mock runner with a controlled worker adapter implementation, but only after these gates exist:

- durable human approval action
- per-platform read-only integration flags
- no-write platform credentials for discovery
- audit logging for every source read
- production write gates with explicit approvals
- tests proving mock evidence cannot trigger production action

Until then, this adapter remains mock-only.
