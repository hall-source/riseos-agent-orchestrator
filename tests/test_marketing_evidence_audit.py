from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.clients.agent_bus import AgentBusAPIError
from app.config import Settings, get_settings
from app.main import app
from app.marketing_evidence_audit import InMemoryMarketingEvidenceAuditRepository
from app.marketing_loop import MARKETING_REPOSITORY, MARKETING_WORKFLOW_TYPE, REVIEW_AGENT
from app.marketing_sheets_evidence_adapter import MarketingSheetsSourceReadError
from app.marketing_sheets_evidence_contract import AttachGoogleSheetsReadOnlyEvidenceRequest


class FakeAuditAgentBusClient:
    def __init__(self, work_items: list[dict[str, object]], *, fail_attach: bool = False) -> None:
        self.work_items = work_items
        self.fail_attach = fail_attach
        self.evidence_packets: dict[str, dict[str, object]] = {}

    async def list_work_items(self, *, repository: str | None = None) -> list[dict[str, object]]:
        return [item for item in self.work_items if repository is None or item.get("repository") == repository]

    async def create_evidence_packet(self, payload: dict[str, object]) -> dict[str, object]:
        evidence_id = f"ev-{uuid4()}"
        packet = {**payload, "evidence_id": evidence_id}
        self.evidence_packets[evidence_id] = packet
        return packet

    async def attach_evidence_to_work_item(self, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        if self.fail_attach:
            raise AgentBusAPIError("POST", f"/work-items/{work_item_id}/evidence", 502, "Agent Bus attach failed")
        item = self._item(work_item_id)
        metadata = item.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata.setdefault("evidence_packet_ids", []).append(payload["evidence_id"])
        return item

    def _item(self, work_item_id: str) -> dict[str, object]:
        for item in self.work_items:
            if item.get("work_item_id") == work_item_id:
                return item
        raise AgentBusAPIError("GET", f"/work-items/{work_item_id}", 404, "Work item not found")


class StaticAuditSheetsReader:
    def __init__(self, *, rows: list[dict[str, object]] | None = None, fail: bool = False) -> None:
        self.rows = rows if rows is not None else [
            {"source": "paid_search", "leads": 18, "contacts_created": 16, "deals_created": 3, "sessions": 450},
            {"source": "organic_search", "leads": 14, "contacts_created": 12, "deals_created": 2, "sessions": 500},
            {"source": "direct", "leads": 10, "contacts_created": 10, "deals_created": 1, "sessions": 250},
        ]
        self.fail = fail

    async def read_rows(self, payload: AttachGoogleSheetsReadOnlyEvidenceRequest) -> list[dict[str, object]]:
        if self.fail:
            raise MarketingSheetsSourceReadError(f"No rows returned from marketing source {payload.source_id}.")
        return self.rows


def marketing_work_item(
    *,
    agent_id: str = "hall-data-intelligence",
    workflow_id: str = "marketing-wf-audit",
) -> dict[str, object]:
    return {
        "work_item_id": f"wi-{uuid4()}",
        "title": f"Marketing work item: {agent_id}",
        "repository": MARKETING_REPOSITORY,
        "status": "queued",
        "owner_agent": agent_id,
        "review_agent": REVIEW_AGENT,
        "metadata": {
            "domain": "marketing",
            "workflow_id": workflow_id,
            "workflow_type": MARKETING_WORKFLOW_TYPE,
            "work_item_role": "specialist_evidence",
            "mock_mode": True,
            "mvp_mode": "mock_only",
            "live_platform_access": False,
            "approval_required": True,
        },
    }


def request_payload(
    work_item_id: str,
    *,
    workflow_id: str = "marketing-wf-audit",
    agent_id: str = "hall-data-intelligence",
    source_id: str = "SAFE_TEST_SOURCE_ABC123",
) -> dict[str, object]:
    return {
        "workflow_id": workflow_id,
        "agent_id": agent_id,
        "work_item_id": work_item_id,
        "source_type": "google_sheet",
        "source_id": source_id,
        "sheet_name": "Weekly Marketing Snapshot",
        "date_range_label": "last_7_days",
    }


def client_with_audit(
    fake_client: FakeAuditAgentBusClient,
    audit_repo: InMemoryMarketingEvidenceAuditRepository,
    *,
    reader: StaticAuditSheetsReader | None = None,
    enable_sheets: bool = True,
    enable_audit: bool = True,
    allowed_source_ids: tuple[str, ...] = ("SAFE_TEST_SOURCE_ABC123",),
    google_application_credentials: str | None = "/secure/test-service-account.json",
) -> TestClient:
    get_settings.cache_clear()
    app.dependency_overrides[get_settings] = lambda: Settings(
        github_webhook_secret="test-secret",
        orchestrator_admin_token="admin-token",
        agent_bus_base_url="http://127.0.0.1:8050",
        enable_marketing_sheets_readonly_evidence=enable_sheets,
        enable_marketing_evidence_audit=enable_audit,
        marketing_readonly_allowed_source_ids=allowed_source_ids,
        google_application_credentials=google_application_credentials,
    )
    app.state.agent_bus_client = fake_client
    app.state.marketing_evidence_audit_repository = audit_repo
    if reader is not None:
        app.state.marketing_sheets_source_reader = reader
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()
    for attr in {"agent_bus_client", "marketing_sheets_source_reader", "marketing_evidence_audit_repository"}:
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    get_settings.cache_clear()


def test_successful_sheets_attach_creates_audit_success_event() -> None:
    item = marketing_work_item()
    audit_repo = InMemoryMarketingEvidenceAuditRepository()
    client = client_with_audit(FakeAuditAgentBusClient([item]), audit_repo, reader=StaticAuditSheetsReader())

    response = client.post(
        "/api/v1/marketing/evidence/google-sheets-readonly/attach",
        headers={"Authorization": "Bearer admin-token"},
        json=request_payload(str(item["work_item_id"])),
    )

    assert response.status_code == 200
    assert len(audit_repo.events) == 1
    event = audit_repo.events[0]
    assert event.status == "success"
    assert event.evidence_packet_id == response.json()["evidence_packet_id"]
    assert event.source_mode == "google_sheets_readonly"
    assert event.write_access is False
    assert event.live_platform_access is False


def test_source_not_allowlisted_creates_audit_failed_event() -> None:
    item = marketing_work_item()
    audit_repo = InMemoryMarketingEvidenceAuditRepository()
    client = client_with_audit(
        FakeAuditAgentBusClient([item]),
        audit_repo,
        reader=None,
        allowed_source_ids=("OTHER_SOURCE",),
    )

    response = client.post(
        "/api/v1/marketing/evidence/google-sheets-readonly/attach",
        headers={"Authorization": "Bearer admin-token"},
        json=request_payload(str(item["work_item_id"])),
    )

    assert response.status_code == 409
    assert audit_repo.events[0].status == "failed"
    assert audit_repo.events[0].allowlist_passed is False
    assert "allowlisted" in str(audit_repo.events[0].failure_reason)


def test_missing_credentials_creates_audit_failed_event() -> None:
    item = marketing_work_item()
    audit_repo = InMemoryMarketingEvidenceAuditRepository()
    client = client_with_audit(
        FakeAuditAgentBusClient([item]),
        audit_repo,
        reader=None,
        google_application_credentials=None,
    )

    response = client.post(
        "/api/v1/marketing/evidence/google-sheets-readonly/attach",
        headers={"Authorization": "Bearer admin-token"},
        json=request_payload(str(item["work_item_id"])),
    )

    assert response.status_code == 502
    assert audit_repo.events[0].status == "failed"
    assert audit_repo.events[0].credentials_present is False
    assert "GOOGLE_APPLICATION_CREDENTIALS" in str(audit_repo.events[0].failure_reason)


def test_unsupported_agent_creates_audit_failed_event() -> None:
    item = marketing_work_item(agent_id="hall-ppc-intelligence")
    audit_repo = InMemoryMarketingEvidenceAuditRepository()
    client = client_with_audit(FakeAuditAgentBusClient([item]), audit_repo, reader=StaticAuditSheetsReader())

    response = client.post(
        "/api/v1/marketing/evidence/google-sheets-readonly/attach",
        headers={"Authorization": "Bearer admin-token"},
        json=request_payload(str(item["work_item_id"]), agent_id="hall-ppc-intelligence"),
    )

    assert response.status_code == 409
    assert audit_repo.events[0].status == "failed"
    assert audit_repo.events[0].agent_id == "hall-ppc-intelligence"
    assert "hall-data-intelligence" in str(audit_repo.events[0].failure_reason)


def test_agent_bus_attach_failure_creates_audit_failed_event() -> None:
    item = marketing_work_item()
    audit_repo = InMemoryMarketingEvidenceAuditRepository()
    client = client_with_audit(
        FakeAuditAgentBusClient([item], fail_attach=True),
        audit_repo,
        reader=StaticAuditSheetsReader(),
    )

    response = client.post(
        "/api/v1/marketing/evidence/google-sheets-readonly/attach",
        headers={"Authorization": "Bearer admin-token"},
        json=request_payload(str(item["work_item_id"])),
    )

    assert response.status_code == 502
    assert audit_repo.events[0].status == "failed"
    assert audit_repo.events[0].evidence_packet_id is None
    assert "Agent Bus attach failed" in str(audit_repo.events[0].failure_reason)


def test_audit_record_redacts_full_source_id() -> None:
    source_id = "SECRET_SOURCE_ABC123"
    item = marketing_work_item()
    audit_repo = InMemoryMarketingEvidenceAuditRepository()
    client = client_with_audit(
        FakeAuditAgentBusClient([item]),
        audit_repo,
        reader=StaticAuditSheetsReader(fail=True),
        allowed_source_ids=(source_id,),
    )

    response = client.post(
        "/api/v1/marketing/evidence/google-sheets-readonly/attach",
        headers={"Authorization": "Bearer admin-token"},
        json=request_payload(str(item["work_item_id"]), source_id=source_id),
    )

    assert response.status_code == 502
    event = audit_repo.events[0]
    event_text = event.model_dump_json()
    assert event.source_id_last_6 == "ABC123"
    assert event.source_id_hash
    assert source_id not in event_text
    assert "[redacted_source_id]" in str(event.failure_reason)


def test_audit_record_never_contains_credentials_or_authorization_header() -> None:
    item = marketing_work_item()
    audit_repo = InMemoryMarketingEvidenceAuditRepository()
    client = client_with_audit(FakeAuditAgentBusClient([item]), audit_repo, reader=StaticAuditSheetsReader())

    response = client.post(
        "/api/v1/marketing/evidence/google-sheets-readonly/attach",
        headers={"Authorization": "Bearer admin-token"},
        json=request_payload(str(item["work_item_id"])),
    )

    assert response.status_code == 200
    event_text = audit_repo.events[0].model_dump_json()
    assert "Bearer" not in event_text
    assert "admin-token" not in event_text
    assert "/secure/test-service-account.json" not in event_text


def test_get_audit_endpoint_requires_admin_auth() -> None:
    audit_repo = InMemoryMarketingEvidenceAuditRepository()
    client = client_with_audit(FakeAuditAgentBusClient([]), audit_repo, reader=StaticAuditSheetsReader())

    response = client.get("/api/v1/marketing/evidence/audit")

    assert response.status_code == 401


def test_get_audit_endpoint_filters_by_workflow_id() -> None:
    item_one = marketing_work_item(workflow_id="workflow-one")
    item_two = marketing_work_item(workflow_id="workflow-two")
    audit_repo = InMemoryMarketingEvidenceAuditRepository()
    client = client_with_audit(
        FakeAuditAgentBusClient([item_one, item_two]),
        audit_repo,
        reader=StaticAuditSheetsReader(),
    )

    for item, workflow_id in [(item_one, "workflow-one"), (item_two, "workflow-two")]:
        response = client.post(
            "/api/v1/marketing/evidence/google-sheets-readonly/attach",
            headers={"Authorization": "Bearer admin-token"},
            json=request_payload(str(item["work_item_id"]), workflow_id=workflow_id),
        )
        assert response.status_code == 200

    response = client.get(
        "/api/v1/marketing/evidence/audit?workflow_id=workflow-one",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["events"]) == 1
    assert body["events"][0]["workflow_id"] == "workflow-one"


def test_feature_flag_disabled_creates_audit_failed_event() -> None:
    item = marketing_work_item()
    audit_repo = InMemoryMarketingEvidenceAuditRepository()
    client = client_with_audit(
        FakeAuditAgentBusClient([item]),
        audit_repo,
        reader=StaticAuditSheetsReader(),
        enable_sheets=False,
    )

    response = client.post(
        "/api/v1/marketing/evidence/google-sheets-readonly/attach",
        headers={"Authorization": "Bearer admin-token"},
        json=request_payload(str(item["work_item_id"])),
    )

    assert response.status_code == 403
    assert audit_repo.events[0].status == "failed"
    assert "ENABLE_MARKETING_SHEETS_READONLY_EVIDENCE" in str(audit_repo.events[0].failure_reason)
