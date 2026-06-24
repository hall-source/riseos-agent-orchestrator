# Current Architecture

## Confirmed Repositories

| Repo | Branch target | Primary language | Package manager |
|---|---|---|---|
| `hall-source/riseos-agent-orchestrator` | `agent-integration` | Python 3.11+ | `pip` / editable install from `pyproject.toml` |
| `hall-source/jarvis-agent-bus-mcp` | `agent-integration` | Python 3.11+ | `pip` / editable install from `pyproject.toml` |

## RiseOS Agent Orchestrator

The orchestrator is a FastAPI service described as a planning-first external automation layer for RiseOS coding agents. Its README states that it accepts GitHub webhooks, verifies GitHub signatures, persists review queue items, hydrates read-only GitHub context, can optionally request BB/Jarvis Architect review decisions from OpenAI, can optionally write comments and labels back to GitHub, and can notify Slack when approved `agent-ready` issues are queued.

### Main entry points

| Area | File or route | Notes |
|---|---|---|
| FastAPI app | `app/main.py` | Creates the app, registers workflow routes, starts storage, defines health and snapshot routes |
| Settings | `app/config.py` | Defines environment-driven feature flags and service URLs |
| Agent Bus client | `app/clients/agent_bus.py` | Wraps Agent Bus `POST /work-items` and `GET /work-items/{id}` |
| Orchestrator snapshot | `app/orchestrator_snapshot.py` | Builds `GET /api/v1/orchestrator/snapshot` response |
| Local run | README | `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` |
| Tests | `pyproject.toml` | `pytest`, with test paths under `tests` |

### Current guardrails

The orchestrator README explicitly says it does not create branches, mutate refs, retarget PRs, merge, deploy, delete branches, close issues, or write repository files. GitHub writeback is limited to comments and labels when explicitly enabled.

The Marketing Agent Loop MVP should preserve these guardrails. It can create Agent Bus work items through the configured Agent Bus API, but should not touch GitHub branches, production systems, marketing platforms, or deployment state.

## Jarvis Agent Bus MCP

Agent Bus is the canonical handoff, work item, agent registry, evidence, review, and mission-control ledger. It exposes FastAPI endpoints plus MCP tool definitions.

### Main entry points

| Area | File or route | Notes |
|---|---|---|
| FastAPI app | `src/agent_bus_mcp/api.py` | Defines health, handoff, agent, work-item, review, and MCP endpoints |
| CLI entry point | `src/agent_bus_mcp/main.py` | Runs `uvicorn agent_bus_mcp.api:app` |
| Core models | `src/agent_bus_mcp/models.py` | Defines agents, work items, handoffs, status enums, and metadata fields |
| Evidence/review lifecycle | `src/agent_bus_mcp/review_lifecycle.py` | Adds evidence packets, review packets, and lifecycle validations |
| Mission Control snapshot | `src/agent_bus_mcp/mission_control.py` | Builds `GET /api/v1/mission-control/snapshot` response |
| Local run | README | `uvicorn agent_bus_mcp.api:app --reload` |
| Tests | `pyproject.toml` | `pytest`, with test paths under `tests` |

## Existing Integration Points

| Integration point | Current state | MVP implication |
|---|---|---|
| Orchestrator to Agent Bus | `AgentBusClient.create_work_item()` exists | First PR can reuse it to create marketing work items |
| Agent registry | Agent Bus exposes `POST /agents`, `GET /agents`, discovery, heartbeat, update, delete | First PR can seed marketing agents through HTTP calls or an internal seed helper |
| Work items | Agent Bus exposes `POST /work-items`, transitions, reviewer assignment, completion | First PR can store each specialist task as a work item |
| Evidence packets | Agent Bus supports canonical evidence packets tied to work items | First PR can attach mock evidence packets without external data sources |
| Mission Control | Agent Bus exposes `GET /api/v1/mission-control/snapshot` | First PR can validate final visibility through this snapshot |
| Orchestrator snapshot | Orchestrator exposes `GET /api/v1/orchestrator/snapshot` | First PR can include marketing workflow visibility or debug state if needed |

## Important Environment Variables

| Variable | Repo | Purpose |
|---|---|---|
| `AGENT_BUS_BASE_URL` | Orchestrator | Agent Bus base URL when dispatch is enabled |
| `AGENT_BUS_TOKEN` | Orchestrator | Optional bearer token for Agent Bus calls |
| `AGENT_BUS_TIMEOUT_SECONDS` | Orchestrator | HTTP timeout for Agent Bus calls |
| `ENABLE_AGENT_BUS_DISPATCH` | Orchestrator | Feature flag for Agent Bus dispatch behavior |
| `ORCHESTRATOR_ADMIN_TOKEN` | Orchestrator | Admin token for protected orchestrator endpoints |
| `ORCHESTRATOR_DB_PATH` | Orchestrator | Optional SQLite persistence path |
| `AGENT_BUS_DB` | Agent Bus | SQLite database location |

## Architecture Assumptions

- The first Marketing Agent Loop should live primarily in `riseos-agent-orchestrator`, because it is workflow orchestration rather than ledger storage.
- Agent Bus should not need a schema change for the first PR if the workflow uses existing `metadata` fields and existing evidence packet models.
- Mission Control visibility should come from Agent Bus first because that is where canonical work items and evidence packets live.

## Risks

- The orchestrator currently has a small Agent Bus client surface. Evidence-packet and agent-registry calls may require adding client methods.
- If Agent Bus lifecycle validation requires evidence before status transitions, the MVP should create evidence before moving specialist work items to `ready_for_review`.
- The final Clone Banks HQ synthesis item may need a clear status convention so it is visible but not mistaken for implementation work.
