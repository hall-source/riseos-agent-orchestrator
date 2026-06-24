# Implementation Backlog

## Priority 0: Documentation And Planning

| Item | Repo | Status |
|---|---|---|
| Convert audit into repo-native CBCA docs | `riseos-agent-orchestrator` | Planned in docs branch |
| Define Marketing Agent Loop MVP PR | `riseos-agent-orchestrator` | Planned in `12-mvp-marketing-loop-pr-plan.md` |
| Confirm Vultr service names and ports | Ops | Open |
| Confirm Agent Bus evidence packet endpoint availability | `jarvis-agent-bus-mcp` | Open |

## Priority 1: Mock Marketing Loop MVP

| Item | Repo | Notes |
|---|---|---|
| Add marketing workflow request/response models | `riseos-agent-orchestrator` | Pydantic models, no live integrations |
| Add admin-protected mock-run endpoint | `riseos-agent-orchestrator` | `POST /api/v1/marketing/weekly-command-brief/mock-run` |
| Extend Agent Bus client methods | `riseos-agent-orchestrator` | Register agents, transition work items, optionally create/attach evidence |
| Add marketing agent registry seed helper | `riseos-agent-orchestrator` | Idempotent registration of six MVP agents |
| Add mock evidence generator | `riseos-agent-orchestrator` | Deterministic packet content |
| Add tests for endpoint and payloads | `riseos-agent-orchestrator` | Use mocked Agent Bus client |
| Add local curl validation docs | `riseos-agent-orchestrator` | Include endpoint and snapshot checks |

## Priority 2: Agent Bus Evidence API Hardening

| Item | Repo | Notes |
|---|---|---|
| Confirm routes for evidence packet creation and attachment | `jarvis-agent-bus-mcp` | The lifecycle model exists; route availability should be verified |
| Add tests for evidence packet visibility in Mission Control | `jarvis-agent-bus-mcp` | If not already covered |
| Add metadata filters for marketing domain if needed | `jarvis-agent-bus-mcp` | Avoid until MVP proves need |
| Add idempotency support for repeated mock runs if needed | Both | Could use `workflow_run_id` or request id |

## Priority 3: Read-Only Platform Discovery

Do not start this until Hall explicitly approves live read-only integration work.

| Platform | First safe scope |
|---|---|
| Google Ads | Read-only account/campaign summary |
| GA4 | Read-only weekly traffic/conversion summary |
| Search Console | Read-only query/page summary |
| HubSpot | Read-only lifecycle/source summary |
| Slack | Notification-only summaries, no workflow action |
| Monday | Read-only board/task summary or explicit approved writeback |

## Priority 4: Human Approval UX

| Item | Notes |
|---|---|
| Approval packet schema | Standardize final Hall approval request |
| Approval state transitions | Add safe states before live writes |
| Mission Control marketing filter | Show marketing runs clearly |
| Reviewer queue view | Show `hall-marketing-reviewer` queue and evidence |

## Priority 5: Live Execution Gates

Only after read-only integrations are stable and Hall approves write behavior.

| Gate | Required proof |
|---|---|
| Live read gate | Credentials stored safely, no writes possible, audit logs available |
| Recommendation gate | Evidence packets use real source labels and confidence levels |
| Write gate | Explicit human approval, dry-run diff, rollback instructions |
| Spend gate | Budget limits, approval record, emergency stop |

## Backlog Guardrails

- Keep changes small and PR-scoped.
- Preserve public APIs until downstream usage is checked.
- Keep Agent Bus canonical for durable state.
- Keep Orchestrator responsible for workflow decisions.
- Avoid new dependencies unless they remove real complexity.
- Treat all marketing recommendations as planning-only until approved.
