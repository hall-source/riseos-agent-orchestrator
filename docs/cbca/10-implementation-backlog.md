# Implementation Backlog

## Priority 0: Documentation And Planning

| Item | Repo | Status |
|---|---|---|
| Convert audit into repo-native CBCA docs | `riseos-agent-orchestrator` | Implemented |
| Define Marketing Agent Loop MVP PR | `riseos-agent-orchestrator` | Implemented in `12-mvp-marketing-loop-pr-plan.md` |
| Confirm Vultr service names and ports | Ops | Open |
| Confirm Agent Bus evidence packet endpoint availability | `jarvis-agent-bus-mcp` | Evidence route used by mock loop |

## Priority 1: Mock Marketing Loop MVP

| Item | Repo | Notes |
|---|---|---|
| Add marketing workflow request/response models | `riseos-agent-orchestrator` | Pydantic models, no live integrations |
| Add admin-protected mock-run endpoint | `riseos-agent-orchestrator` | `POST /api/v1/marketing/weekly-command-brief/mock-run` |
| Extend Agent Bus client methods | `riseos-agent-orchestrator` | Register agents, create work, attach evidence/review artifacts |
| Add marketing agent registry seed helper | `riseos-agent-orchestrator` | Idempotent registration of six MVP agents |
| Add mock evidence generator | `riseos-agent-orchestrator` | Deterministic packet content |
| Add canonical mock review and HQ synthesis artifacts | `riseos-agent-orchestrator` | `risk_review` and `synthesis_memo` artifacts |
| Add tests for endpoint and payloads | `riseos-agent-orchestrator` | Use mocked Agent Bus client |
| Add local curl validation docs | `riseos-agent-orchestrator` | Include endpoint and snapshot checks |

## Priority 1A: Marketing Worker Adapter Contract

| Item | Repo | Notes |
|---|---|---|
| Add marketing worker registry | `riseos-agent-orchestrator` | Routing/validation only, live integrations disabled |
| Add worker adapter contract models | `riseos-agent-orchestrator` | Run-once request/response and per-item result |
| Add callable mock worker adapter | `riseos-agent-orchestrator` | Poll, claim, mark in progress, attach evidence, complete |
| Add admin-protected run-once endpoint | `riseos-agent-orchestrator` | `POST /api/v1/marketing/workers/mock/run-once` |
| Add safe execution flag | `riseos-agent-orchestrator` | `ENABLE_MARKETING_WORKER_MOCK=true` required |
| Add deferred specialist completion option | `riseos-agent-orchestrator` | `auto_complete_specialists=false` lets worker attach evidence |
| Add worker adapter tests | `riseos-agent-orchestrator` | Registry, eligibility, safety flags, endpoint auth |

## Priority 1B: Marketing Governance Stage Runner

| Item | Repo | Notes |
|---|---|---|
| Add governance run contract models | `riseos-agent-orchestrator` | Run-once request/response and reviewer/HQ stage results |
| Add callable mock governance runner | `riseos-agent-orchestrator` | Validates specialist evidence, then creates review and synthesis artifacts |
| Add admin-protected governance endpoint | `riseos-agent-orchestrator` | `POST /api/v1/marketing/governance/mock/run-once` |
| Add safe execution flag | `riseos-agent-orchestrator` | `ENABLE_MARKETING_GOVERNANCE_MOCK=true` required |
| Update summary next actions | `riseos-agent-orchestrator` | Worker first, then reviewer/HQ, then Hall review |
| Add governance runner tests | `riseos-agent-orchestrator` | Auth, flag, evidence validation, artifact references, mock safeguards |

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
