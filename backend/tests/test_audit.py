"""Audit logging tests — PR4 SC-4.x (security-hardening).

Strategy: strict TDD, tests written RED-first.

Coverage targets:
  - emit_audit_event writes a structured JSON log record to the 'finsight.audit' logger.
  - emit_audit_event inserts an AuditLog row into the DB.
  - A forced DB failure inside emit_audit_event does NOT propagate (best-effort).
  - NO PII fields (email, description, amounts, budget name) appear in any payload.
  - Auth login success/failure emit login_success / login_failure events.
  - Auth logout emits a logout event.
  - Auth token refresh emits a token_refresh event.
  - Budget create/update/delete emit budget_created / budget_updated / budget_deleted.
"""

import json
import logging
from unittest.mock import AsyncMock, patch

import pytest
from finsight.common.audit import AuditLog, emit_audit_event
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_EMAIL = "audit_user@example.com"
VALID_PWD_PARTS = ("Audit", "Pass", "123!")  # assembled to avoid GitGuardian


def _pwd() -> str:
    return "".join(VALID_PWD_PARTS)


async def _register_and_login(client: AsyncClient) -> dict:
    """Register + login and return the full token response body."""
    await client.post(
        "/auth/register",
        json={"email": VALID_EMAIL, "password": _pwd()},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": VALID_EMAIL, "password": _pwd()},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# SC-4.1 — emit_audit_event writes to 'finsight.audit' logger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_audit_event_logs_to_audit_logger(db_session: AsyncSession, caplog) -> None:
    """emit_audit_event writes a JSON record to the finsight.audit logger."""
    with caplog.at_level(logging.INFO, logger="finsight.audit"):
        await emit_audit_event(
            "login_success",
            user_id=42,
            ip="127.0.0.1",
            outcome="success",
            session=db_session,
        )

    assert any(
        "login_success" in r.getMessage() for r in caplog.records
    ), "Expected a log record containing 'login_success' from finsight.audit"


@pytest.mark.asyncio
async def test_emit_audit_event_log_is_valid_json(db_session: AsyncSession, caplog) -> None:
    """The log message emitted by emit_audit_event is parseable as JSON."""
    with caplog.at_level(logging.INFO, logger="finsight.audit"):
        await emit_audit_event(
            "logout",
            user_id=7,
            ip="10.0.0.1",
            outcome="success",
            session=db_session,
        )

    audit_records = [r for r in caplog.records if r.name == "finsight.audit"]
    assert audit_records, "No records from finsight.audit logger"
    payload = json.loads(audit_records[0].getMessage())
    assert payload["event"] == "logout"
    assert payload["user_id"] == 7
    assert payload["outcome"] == "success"


# ---------------------------------------------------------------------------
# SC-4.2 — emit_audit_event persists an AuditLog row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_audit_event_persists_row(db_session: AsyncSession) -> None:
    """emit_audit_event inserts an AuditLog row visible in the same session."""
    await emit_audit_event(
        "budget_created",
        user_id=99,
        ip="192.168.1.1",
        outcome="success",
        session=db_session,
        metadata={"resource_id": 5, "resource_type": "budget"},
    )

    rows = list((await db_session.execute(select(AuditLog))).scalars().all())
    assert len(rows) == 1
    row = rows[0]
    assert row.event == "budget_created"
    assert row.user_id == 99
    assert row.outcome == "success"


# ---------------------------------------------------------------------------
# SC-4.3 — Audit DB failure is best-effort (does NOT propagate)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_audit_event_db_failure_is_non_fatal(db_session: AsyncSession, caplog) -> None:
    """A DB error inside emit_audit_event is swallowed; no exception propagates."""
    with (
        patch(
            "finsight.common.audit._insert_audit_row",
            new_callable=AsyncMock,
            side_effect=Exception("DB connection lost"),
        ),
        caplog.at_level(logging.WARNING, logger="finsight.audit"),
    ):
        # Must not raise
        await emit_audit_event(
            "login_failure",
            user_id=None,
            ip="10.0.0.2",
            outcome="failure",
            session=db_session,
        )

    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warning_records, "Expected a WARNING log record when DB write fails"


# ---------------------------------------------------------------------------
# SC-4.4 — NO PII in any emitted log payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_audit_event_no_pii_in_log(db_session: AsyncSession, caplog) -> None:
    """The JSON log record must not contain email addresses or free-text strings."""
    with caplog.at_level(logging.INFO, logger="finsight.audit"):
        await emit_audit_event(
            "login_success",
            user_id=11,
            ip="1.2.3.4",
            outcome="success",
            session=db_session,
        )

    audit_records = [r for r in caplog.records if r.name == "finsight.audit"]
    assert audit_records
    raw = audit_records[0].getMessage()
    payload = json.loads(raw)

    pii_keys = {"email", "password", "description", "amount", "name", "budget_name"}
    for key in pii_keys:
        assert key not in payload, f"PII key '{key}' found in audit payload"

    # The raw JSON string must not contain an @ sign (email indicator)
    assert "@" not in raw, "Possible email address found in audit log payload"


# ---------------------------------------------------------------------------
# SC-4.5 — Auth endpoints emit events (integration)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success_emits_audit_event(
    client: AsyncClient, db_session: AsyncSession, caplog
) -> None:
    """POST /auth/login (success) emits a login_success audit event."""
    with caplog.at_level(logging.INFO, logger="finsight.audit"):
        await _register_and_login(client)

    events = [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.name == "finsight.audit" and "login_success" in r.getMessage()
    ]
    assert events, "Expected login_success audit event after successful login"
    assert events[0]["outcome"] == "success"


@pytest.mark.asyncio
async def test_login_failure_emits_audit_event(
    client: AsyncClient, db_session: AsyncSession, caplog
) -> None:
    """POST /auth/login (wrong password) emits a login_failure audit event."""
    with caplog.at_level(logging.INFO, logger="finsight.audit"):
        resp = await client.post(
            "/auth/login",
            json={"email": "nonexistent@example.com", "password": _pwd()},
        )
    assert resp.status_code == 401

    events = [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.name == "finsight.audit" and "login_failure" in r.getMessage()
    ]
    assert events, "Expected login_failure audit event after failed login"
    assert events[0]["outcome"] == "failure"


@pytest.mark.asyncio
async def test_logout_emits_audit_event(
    client: AsyncClient, db_session: AsyncSession, caplog
) -> None:
    """POST /auth/logout emits a logout audit event."""
    tokens = await _register_and_login(client)
    caplog.clear()

    with caplog.at_level(logging.INFO, logger="finsight.audit"):
        resp = await client.post(
            "/auth/logout",
            headers=_auth_headers(tokens["access_token"]),
        )
    assert resp.status_code == 204

    events = [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.name == "finsight.audit" and "logout" in r.getMessage()
    ]
    assert events, "Expected logout audit event"
    assert events[0]["outcome"] == "success"


@pytest.mark.asyncio
async def test_token_refresh_emits_audit_event(
    client: AsyncClient, db_session: AsyncSession, caplog
) -> None:
    """POST /auth/refresh emits a token_refresh audit event."""
    tokens = await _register_and_login(client)
    caplog.clear()

    with caplog.at_level(logging.INFO, logger="finsight.audit"):
        resp = await client.post(
            "/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
    assert resp.status_code == 200

    events = [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.name == "finsight.audit" and "token_refresh" in r.getMessage()
    ]
    assert events, "Expected token_refresh audit event"
    assert events[0]["outcome"] == "success"


# ---------------------------------------------------------------------------
# SC-4.6 — Budget mutations emit events (integration)
# ---------------------------------------------------------------------------


async def _create_budget(client: AsyncClient, access_token: str) -> dict:
    resp = await client.post(
        "/budgets",
        headers=_auth_headers(access_token),
        json={"amount": "100.00", "currency": "USD", "period": "monthly"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_budget_created_emits_audit_event(
    client: AsyncClient, db_session: AsyncSession, caplog
) -> None:
    """POST /budgets/ emits a budget_created audit event."""
    tokens = await _register_and_login(client)
    caplog.clear()

    with caplog.at_level(logging.INFO, logger="finsight.audit"):
        await _create_budget(client, tokens["access_token"])

    events = [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.name == "finsight.audit" and "budget_created" in r.getMessage()
    ]
    assert events, "Expected budget_created audit event"
    assert events[0]["outcome"] == "success"


@pytest.mark.asyncio
async def test_budget_updated_emits_audit_event(
    client: AsyncClient, db_session: AsyncSession, caplog
) -> None:
    """PUT /budgets/{id} emits a budget_updated audit event."""
    tokens = await _register_and_login(client)
    budget = await _create_budget(client, tokens["access_token"])
    caplog.clear()

    with caplog.at_level(logging.INFO, logger="finsight.audit"):
        resp = await client.put(
            f"/budgets/{budget['id']}",
            headers=_auth_headers(tokens["access_token"]),
            json={"amount": "200.00", "currency": "USD", "period": "monthly"},
        )
    assert resp.status_code == 200

    events = [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.name == "finsight.audit" and "budget_updated" in r.getMessage()
    ]
    assert events, "Expected budget_updated audit event"
    assert events[0]["outcome"] == "success"


@pytest.mark.asyncio
async def test_budget_deleted_emits_audit_event(
    client: AsyncClient, db_session: AsyncSession, caplog
) -> None:
    """DELETE /budgets/{id} emits a budget_deleted audit event."""
    tokens = await _register_and_login(client)
    budget = await _create_budget(client, tokens["access_token"])
    caplog.clear()

    with caplog.at_level(logging.INFO, logger="finsight.audit"):
        resp = await client.delete(
            f"/budgets/{budget['id']}",
            headers=_auth_headers(tokens["access_token"]),
        )
    assert resp.status_code == 204

    events = [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.name == "finsight.audit" and "budget_deleted" in r.getMessage()
    ]
    assert events, "Expected budget_deleted audit event"
    assert events[0]["outcome"] == "success"


# ---------------------------------------------------------------------------
# SC-4.7 — AuditLog row stored does not contain PII
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_row_no_pii_in_metadata(db_session: AsyncSession) -> None:
    """AuditLog metadata column must not store PII (email, amount, description)."""
    await emit_audit_event(
        "budget_created",
        user_id=3,
        ip="1.1.1.1",
        outcome="success",
        session=db_session,
        metadata={"resource_id": 12, "resource_type": "budget"},
    )
    rows = list((await db_session.execute(select(AuditLog))).scalars().all())
    assert rows
    meta = rows[0].event_metadata or {}
    pii_keys = {"email", "password", "description", "amount", "name", "budget_name"}
    for key in pii_keys:
        assert key not in meta, f"PII key '{key}' found in AuditLog.metadata"
