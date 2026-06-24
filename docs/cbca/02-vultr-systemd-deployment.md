# Vultr Systemd Deployment

## Scope

This document captures deployment assumptions and validation commands for the current Orchestrator and Agent Bus services. It does not authorize production changes, restarts, migrations, or secret edits.

## Confirmed Local Startup Commands

### RiseOS Agent Orchestrator

```bash
cd /path/to/riseos-agent-orchestrator
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
export GITHUB_WEBHOOK_SECRET='dev-secret'
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Jarvis Agent Bus MCP

```bash
cd /path/to/jarvis-agent-bus-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export AGENT_BUS_DB="$PWD/.local/agent_bus.db"
uvicorn agent_bus_mcp.api:app --host 0.0.0.0 --port 8001
```

If both services are on the same machine, run them on different ports. The docs use `8000` for Orchestrator and `8001` for Agent Bus.

## Expected Systemd Shape

The repo audit did not verify a committed systemd unit file in the checked files. A typical Vultr deployment should have separate units for each service.

| Service | Expected process | Expected port |
|---|---|---:|
| Orchestrator | `uvicorn app.main:app --host 0.0.0.0 --port 8000` | `8000` |
| Agent Bus | `uvicorn agent_bus_mcp.api:app --host 0.0.0.0 --port 8001` or `agent-bus-api` with configured port | `8001` |

## Environment File Guidance

Use environment files owned by the server operator, not committed secrets.

### Orchestrator minimum local/MVP variables

```bash
APP_ENV=local
GITHUB_WEBHOOK_SECRET=dev-secret
ORCHESTRATOR_DB_PATH=/var/lib/riseos-agent-orchestrator/orchestrator.db
ORCHESTRATOR_ADMIN_TOKEN=replace-with-secret
AGENT_BUS_BASE_URL=http://127.0.0.1:8001
ENABLE_AGENT_BUS_DISPATCH=true
```

### Agent Bus minimum local/MVP variables

```bash
AGENT_BUS_DB=/var/lib/jarvis-agent-bus-mcp/agent_bus.db
```

## Health Validation

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8001/health
```

Expected response for both:

```json
{"status":"ok"}
```

## Snapshot Validation

```bash
curl -sS http://127.0.0.1:8000/api/v1/orchestrator/snapshot | jq .
curl -sS http://127.0.0.1:8001/api/v1/mission-control/snapshot | jq .
```

If debug reads require an admin token on the orchestrator:

```bash
curl -sS http://127.0.0.1:8000/api/v1/orchestrator/snapshot \
  -H "X-Orchestrator-Admin-Token: $ORCHESTRATOR_ADMIN_TOKEN" | jq .
```

## Systemd Read-Only Inspection Commands

Marcus can run these on Vultr to inspect status without changing production state:

```bash
systemctl status riseos-agent-orchestrator --no-pager
systemctl status jarvis-agent-bus-mcp --no-pager
journalctl -u riseos-agent-orchestrator -n 100 --no-pager
journalctl -u jarvis-agent-bus-mcp -n 100 --no-pager
systemctl cat riseos-agent-orchestrator
systemctl cat jarvis-agent-bus-mcp
```

## Deployment Safety Notes

- Do not paste real tokens into docs, PRs, logs, or issues.
- Do not restart services during documentation review unless Hall approves.
- Do not enable live marketing integrations for the MVP.
- Keep `ENABLE_GITHUB_WRITEBACK`, `ENABLE_TASK_DISPATCH`, and any future marketing-platform flags disabled unless explicitly approved.

## Open Deployment Questions

| Question | Owner |
|---|---|
| What are the exact Vultr service names? | Marcus |
| Which ports are currently bound by Orchestrator and Agent Bus? | Marcus |
| Are both services on the same host, or split across hosts? | Marcus |
| Where are environment files stored on Vultr? | Marcus |
| Is there a reverse proxy route for mission-control/snapshot? | Hall / Marcus |
