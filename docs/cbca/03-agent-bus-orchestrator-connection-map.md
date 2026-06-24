# Agent Bus Orchestrator Connection Map

## Responsibility Boundary

| Concern | RiseOS Agent Orchestrator | Jarvis Agent Bus MCP |
|---|---|---|
| Decide when a workflow should start | Yes | No |
| Interpret manual or webhook triggers | Yes | No |
| Create durable work items | Calls Agent Bus | Stores canonical records |
| Register/discover agents | May seed or query | Owns registry |
| Attach evidence | Calls Agent Bus | Stores canonical packets |
| Assign reviewer | Calls Agent Bus | Stores reviewer assignment |
| Synthesize final command brief | Orchestrates and creates item | Stores HQ synthesis work item |
| Mission Control visibility | May expose orchestrator state | Canonical work/evidence snapshot |
| Live platform writes | Not in MVP | Not in MVP |

## Current Confirmed APIs

### Orchestrator

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/health` | Service health |
| `POST` | `/api/v1/agent-tasks` | Admin-protected task submission shell |
| `GET` | `/api/v1/orchestrator/snapshot` | Orchestrator workforce/workflow snapshot |
| `GET` | `/debug/repositories` | Repository diagnostics |
| `GET` | `/debug/review-queue` | Review queue visibility, per README |
| `POST` | `/debug/review-queue/{id}/process` | Admin-protected dry-run processing, per README |

### Agent Bus

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/health` | Service health |
| `POST` | `/agents` | Register agent |
| `GET` | `/agents` | List/filter agents |
| `GET` | `/agents/discover` | Discover agents by capability/type/status |
| `POST` | `/agents/heartbeat` | Update agent presence |
| `POST` | `/work-items` | Create canonical work item |
| `GET` | `/work-items` | List/filter work items |
| `GET` | `/work-items/{id}` | Work item detail |
| `POST` | `/work-items/{id}/transition` | Move work item through lifecycle |
| `POST` | `/work-items/{id}/assign-reviewer` | Assign reviewer |
| `POST` | `/reviews/{work_item_id}/claim` | Claim review |
| `GET` | `/api/v1/mission-control/snapshot` | Mission Control snapshot |
| `GET` | `/mcp/tools` | MCP tool definitions |
| `POST` | `/mcp/call` | MCP tool call bridge |

## Proposed Marketing MVP Flow

```text
Hall or Marcus requests weekly marketing command brief
  |
  v
Orchestrator endpoint validates admin token and request metadata
  |
  v
Orchestrator ensures six marketing agents exist in Agent Bus
  |
  v
Orchestrator creates specialist work items in Agent Bus
  |
  v
Mock evidence function creates evidence packets for each specialist item
  |
  v
Orchestrator transitions specialist items to ready_for_review
  |
  v
Orchestrator creates reviewer work item assigned to hall-marketing-reviewer
  |
  v
Mock review/evidence function summarizes specialist packets
  |
  v
Orchestrator creates clone-banks-hq synthesis work item
  |
  v
Mission Control snapshot shows agents, queue counts, evidence count, review state
```

## Work Item Relationships

Use a shared `correlation_id` and metadata fields to connect the workflow.

```json
{
  "domain": "marketing",
  "brand": "rise",
  "business_unit": "RISE Commercial District",
  "workflow_type": "weekly_marketing_command_brief",
  "source_event": "manual_request",
  "approval_required": true,
  "human_owner": "Hall",
  "review_agent": "hall-marketing-reviewer",
  "workflow_run_id": "uuid",
  "parent_work_item_id": null,
  "depends_on_work_item_ids": [],
  "output_kind": "specialist_evidence"
}
```

## Recommended First Endpoint

Prefer a new admin-protected orchestrator endpoint for clarity:

```text
POST /api/v1/marketing/weekly-command-brief/mock-run
```

Reason: the trigger is a manual business workflow request, not a GitHub webhook, not an issue dispatch, and not a debug-only review queue processor.

## Existing Endpoint Alternative

`POST /api/v1/agent-tasks` could be reused, but it currently accepts generic repository task fields and does not express marketing workflow metadata, specialist fan-out, evidence generation, or synthesis behavior. Reusing it would make the MVP less obvious to operators.

## Data Flow Contracts

| Object | Created by | Stored in | Visibility |
|---|---|---|---|
| Marketing workflow request | Orchestrator | Orchestrator response and work item metadata | Orchestrator logs/snapshot if implemented |
| Specialist work item | Orchestrator | Agent Bus | Mission Control snapshot |
| Mock evidence packet | Orchestrator fake worker function | Agent Bus | Mission Control evidence metrics and work item detail |
| Reviewer work item | Orchestrator | Agent Bus | Mission Control snapshot/review queue |
| HQ synthesis item | Orchestrator | Agent Bus | Mission Control snapshot |

## Implementation Notes

- Keep all marketing-specific fields in metadata for the first PR.
- Use existing Agent Bus status enum values: `queued`, `in_progress`, `awaiting_evidence`, `ready_for_review`, `review_in_progress`, `approved`, `completed`, `blocked`, `failed`.
- Avoid new database tables unless a metadata-only approach blocks Mission Control visibility.
- Return the created Agent Bus IDs from the orchestrator endpoint for easy validation.
