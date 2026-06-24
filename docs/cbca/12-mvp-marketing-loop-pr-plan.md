# MVP Marketing Loop PR Plan

## PR Goal

Build the first mock-only Marketing Agent Loop in `riseos-agent-orchestrator` without connecting live marketing platforms.

The PR should prove this loop:

```text
manual marketing command brief request
-> orchestrator creates mock/simulated specialist work items
-> Agent Bus stores work items
-> fake worker/evidence function attaches evidence packets
-> reviewer work item is created
-> Clone Banks HQ synthesis item is created
-> final state is visible through mission-control/snapshot
```

## Required Agents

```text
clone-banks-hq
hall-data-intelligence
hall-ppc-intelligence
hall-seo-intelligence
hall-creative-strategist
hall-marketing-reviewer
```

## Required Metadata Convention

```json
{
  "domain": "marketing",
  "brand": "rise",
  "business_unit": "RISE Commercial District",
  "workflow_type": "weekly_marketing_command_brief",
  "source_event": "manual_request",
  "approval_required": true,
  "human_owner": "Hall",
  "review_agent": "hall-marketing-reviewer"
}
```

## Proposed PR Title

```text
Add mock Marketing Agent Loop MVP
```

## Proposed Branch

```text
CBCA/mock-marketing-loop-mvp
```

## Files Likely To Change

### `riseos-agent-orchestrator`

| File | Change |
|---|---|
| `app/main.py` | Register marketing routes or include route module |
| `app/config.py` | Add optional `MARKETING_MVP_ENABLED` flag only if Hall wants explicit gating; default false if added |
| `app/clients/agent_bus.py` | Add client methods for `POST /agents`, `POST /agents/heartbeat`, `POST /work-items/{id}/transition`, and evidence/review packet operations if routes exist |
| `app/marketing_loop.py` | New service module for orchestration logic, agent seeding, work-item fan-out, mock evidence, reviewer item, and HQ synthesis item |
| `app/marketing_routes.py` | New FastAPI routes and request/response models |
| `tests/test_marketing_loop.py` | Unit tests for orchestration service with mocked Agent Bus client |
| `tests/test_marketing_routes.py` | API tests for auth, request validation, and response shape |
| `README.md` or `docs/cbca/09-weekly-marketing-command-brief-mvp.md` | Add curl validation if implementation changes endpoint specifics |

### `jarvis-agent-bus-mcp`

No required code change should be made in the first PR unless inspection shows Agent Bus does not expose evidence/review packet routes needed by the MVP. If a change is necessary, keep it to route exposure for already-defined evidence/review lifecycle models.

Potential files only if needed:

| File | Change |
|---|---|
| `src/agent_bus_mcp/api.py` | Expose create/attach evidence packet routes if missing |
| `tests/test_review_lifecycle.py` | Add route-level coverage for evidence packet creation and attachment |

## New Endpoint Proposal

Add an admin-protected route to the orchestrator:

```text
POST /api/v1/marketing/weekly-command-brief/mock-run
```

### Request

```json
{
  "brand": "rise",
  "business_unit": "RISE Commercial District",
  "human_owner": "Hall",
  "requested_by": "Marcus",
  "period_start": "2026-06-17",
  "period_end": "2026-06-24"
}
```

### Response

```json
{
  "accepted": true,
  "mode": "mock_only",
  "workflow_run_id": "uuid",
  "metadata": {
    "domain": "marketing",
    "brand": "rise",
    "business_unit": "RISE Commercial District",
    "workflow_type": "weekly_marketing_command_brief",
    "source_event": "manual_request",
    "approval_required": true,
    "human_owner": "Hall",
    "review_agent": "hall-marketing-reviewer"
  },
  "agent_seed_results": [
    {"agent_id": "clone-banks-hq", "status": "registered_or_existing"}
  ],
  "specialist_work_items": [
    {"agent_id": "hall-data-intelligence", "work_item_id": "uuid", "evidence_packet_id": "uuid"}
  ],
  "reviewer_work_item": {"agent_id": "hall-marketing-reviewer", "work_item_id": "uuid"},
  "synthesis_work_item": {"agent_id": "clone-banks-hq", "work_item_id": "uuid"},
  "mock_only_notice": "No live marketing platforms were connected or modified."
}
```

## Existing Endpoint Option

`POST /api/v1/agent-tasks` could be reused, but it should not be the default choice because:

- It is repository-task oriented, not marketing-workflow oriented.
- It does not express specialist fan-out.
- It does not express mock evidence generation.
- It does not naturally return the created Agent Bus work item IDs.

Use it only if Hall rejects adding a marketing-specific endpoint.

## Agent Registry Seed Method

Add an idempotent seed helper in `app/marketing_loop.py`:

```python
MARKETING_AGENTS = [
    {
        "agent_id": "clone-banks-hq",
        "agent_type": "orchestration",
        "capabilities": ["marketing_synthesis", "executive_brief", "human_handoff"],
    },
    {
        "agent_id": "hall-data-intelligence",
        "agent_type": "marketing_specialist",
        "capabilities": ["analytics", "measurement", "kpi_summary", "mock_evidence"],
    },
    {
        "agent_id": "hall-ppc-intelligence",
        "agent_type": "marketing_specialist",
        "capabilities": ["paid_search", "paid_media", "campaign_analysis", "mock_evidence"],
    },
    {
        "agent_id": "hall-seo-intelligence",
        "agent_type": "marketing_specialist",
        "capabilities": ["seo", "content_gap", "search_intent", "mock_evidence"],
    },
    {
        "agent_id": "hall-creative-strategist",
        "agent_type": "marketing_specialist",
        "capabilities": ["creative_strategy", "offer_strategy", "message_testing", "mock_evidence"],
    },
    {
        "agent_id": "hall-marketing-reviewer",
        "agent_type": "review",
        "capabilities": ["marketing_review", "risk_review", "approval_gate", "human_handoff"],
    },
]
```

Seed behavior:

1. Register each agent through Agent Bus `POST /agents`.
2. Treat duplicate-agent conflicts as `registered_or_existing`.
3. Send heartbeat if the Agent Bus client supports it.
4. Include `mvp_mode=mock_only` and `live_platform_access=false` in agent metadata.

## Mock Evidence Packet Format

```json
{
  "work_item_id": "uuid",
  "repository": "hall-source/riseos-agent-orchestrator",
  "issue_number": null,
  "pr_number": null,
  "implementation_agent": "hall-seo-intelligence",
  "branch": "agent-integration",
  "commit_shas": [],
  "changed_files": [],
  "test_commands": ["mock-marketing-loop"],
  "test_results": {
    "mode": "mock_only",
    "source_systems": ["mock"],
    "live_platform_access": false,
    "evidence_schema": "marketing.mock_evidence.v1",
    "findings": ["Mock finding for validation."],
    "recommended_actions": ["Planning-only recommendation requiring Hall approval."]
  },
  "verification_summary": "Mock SEO evidence generated for Marketing Agent Loop MVP validation.",
  "assumptions": ["No live platform data was used."],
  "unverified_items": ["Live Search Console data is not connected."]
}
```

If Agent Bus evidence routes are unavailable, store the same object under work-item metadata as `mock_evidence` and open a follow-up issue to expose the evidence lifecycle routes.

## Proposed Implementation Steps

1. Inspect Agent Bus route coverage for evidence and review packets.
2. Add missing Agent Bus client methods in the orchestrator.
3. Add `app/marketing_loop.py` with pure orchestration helpers.
4. Add `app/marketing_routes.py` with an admin-protected mock-run endpoint.
5. Register the route from `app/main.py`.
6. Add tests with a fake Agent Bus client.
7. Run orchestrator tests.
8. Optionally run local integration validation with Agent Bus and Orchestrator services.

## Test Plan

### Unit tests

- Request validation rejects unsupported brand values.
- Request validation forces `approval_required=true` behavior.
- Agent seeding registers all six required agents.
- Duplicate agent registration is treated as success.
- Four specialist work items are created.
- Four mock evidence packets are created or stored in metadata.
- Reviewer work item depends on specialist IDs.
- HQ synthesis item depends on specialist and reviewer IDs.
- Response includes workflow run ID and all created IDs.
- No live platform client is called.

### Integration tests

With local Agent Bus running:

- Run endpoint once.
- Fetch Agent Bus work items.
- Fetch Mission Control snapshot.
- Confirm agents, queue counts, and evidence metrics changed.

### Regression tests

- Existing `pytest` suite in `riseos-agent-orchestrator` passes.
- If Agent Bus routes change, existing `jarvis-agent-bus-mcp` tests pass.

## Local Validation Commands

### Start Agent Bus

```bash
cd /path/to/jarvis-agent-bus-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
mkdir -p .local
export AGENT_BUS_DB="$PWD/.local/agent_bus.db"
uvicorn agent_bus_mcp.api:app --host 0.0.0.0 --port 8001
```

### Start Orchestrator

```bash
cd /path/to/riseos-agent-orchestrator
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
export GITHUB_WEBHOOK_SECRET='dev-secret'
export ORCHESTRATOR_ADMIN_TOKEN='dev-admin-token'
export AGENT_BUS_BASE_URL='http://127.0.0.1:8001'
export ENABLE_AGENT_BUS_DISPATCH='true'
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Health checks

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8001/health
```

### Run mock marketing loop

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/marketing/weekly-command-brief/mock-run \
  -H "Content-Type: application/json" \
  -H "X-Orchestrator-Admin-Token: $ORCHESTRATOR_ADMIN_TOKEN" \
  -d '{
    "brand": "rise",
    "business_unit": "RISE Commercial District",
    "human_owner": "Hall",
    "requested_by": "Marcus",
    "period_start": "2026-06-17",
    "period_end": "2026-06-24"
  }' | jq .
```

### Validate Agent Bus state

```bash
curl -sS http://127.0.0.1:8001/agents | jq '.[] | select(.metadata.domain == "marketing")'
curl -sS 'http://127.0.0.1:8001/work-items?repository=hall-source/riseos-agent-orchestrator' | jq .
curl -sS http://127.0.0.1:8001/api/v1/mission-control/snapshot | jq .
```

### Validate Orchestrator snapshot

```bash
curl -sS http://127.0.0.1:8000/api/v1/orchestrator/snapshot \
  -H "X-Orchestrator-Admin-Token: $ORCHESTRATOR_ADMIN_TOKEN" | jq .
```

## Vultr Validation Commands

Use real service hostnames/ports from Marcus. Do not paste real secrets into shell history if avoidable.

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8001/health
curl -sS http://127.0.0.1:8001/api/v1/mission-control/snapshot | jq .
systemctl status riseos-agent-orchestrator --no-pager
systemctl status jarvis-agent-bus-mcp --no-pager
journalctl -u riseos-agent-orchestrator -n 100 --no-pager
journalctl -u jarvis-agent-bus-mcp -n 100 --no-pager
```

## Risks

| Risk | Mitigation |
|---|---|
| Agent Bus evidence routes may not be exposed even though models exist | Inspect first; fallback to work-item metadata or add tiny route PR |
| Endpoint could be mistaken for live marketing automation | Use `mock-run` in route and `mock_only` in response/metadata |
| Repeated runs may clutter Mission Control | Accept for MVP or add optional request label/filter later |
| Status transitions may require evidence/review packet conditions | Create evidence before moving to `ready_for_review` |
| Agent seeding duplicates could fail | Treat duplicate conflict as success |
| Public behavior changes accidentally enabled | Keep endpoint admin-protected and do not add background jobs |

## Rollback Plan

- Disable or remove the orchestrator marketing route registration.
- Delete no data by default; existing mock Agent Bus records can remain as audit evidence.
- If a clean local reset is required, stop services and remove only local dev SQLite files such as `.local/agent_bus.db` and `.local/orchestrator.db`.
- Revert the PR if it causes unexpected runtime behavior.
- No live marketing platform rollback is needed because the MVP must not connect to live platforms.

## Questions For Hall Or Marcus

| Question | Owner |
|---|---|
| Approve new endpoint `POST /api/v1/marketing/weekly-command-brief/mock-run`? | Hall |
| Should the endpoint require date fields or default to the trailing 7 days? | Hall |
| Should reviewer output be `approved` or `pending_human` after mock run? | Hall |
| What are the exact Vultr service names and ports? | Marcus |
| Is Agent Bus running with persistent `AGENT_BUS_DB` on Vultr? | Marcus |
| Should the first PR include any Agent Bus route exposure if evidence routes are missing? | Hall / Marcus |

## Definition Of Done

- Documentation remains unchanged except endpoint-specific updates if needed.
- Orchestrator tests pass.
- No live marketing platform credentials or clients are added.
- Local mock run creates visible Agent Bus state.
- Mission Control snapshot shows the run aftermath.
- PR description includes `Verified`, `Assumed`, and `Unverifed` sections.
