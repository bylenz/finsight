"""Audit logging — emit structured events to stdout + persist AuditLog rows.

Design decisions (PR4, security-hardening):
  - ``emit_audit_event`` is BEST-EFFORT: DB write failures are caught, logged at
    WARNING, and never re-raised. The caller's transaction is never rolled back.
  - NO PII: the payload and metadata must never contain email addresses, expense
    descriptions, amounts, budget names, or any free-text user-supplied strings.
    Allowed fields: event name, user_id (int), ip, outcome, timestamp, resource
    ids/types, HTTP status codes, boolean flags, token jti.
  - The audit logger name is ``finsight.audit``; configure its handler in
    production to ship to a log aggregator.
  - The ``AuditLog`` ORM model uses SQLAlchemy generic JSON for the ``metadata``
    column so it maps to TEXT in SQLite (tests) and JSONB in Postgres (prod).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from finsight.db import Base

_audit_logger = logging.getLogger("finsight.audit")

# ---------------------------------------------------------------------------
# ORM Model
# ---------------------------------------------------------------------------


class AuditLog(Base):
    """Persisted audit trail row — one row per significant security event."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    # Generic JSON — TEXT in SQLite, JSONB in Postgres (via SA dialect adaptation).
    # Use SQLAlchemy's generic JSON type (NOT pg.JSONB) for portability.
    # Attribute is `event_metadata` because `metadata` is reserved by the
    # SQLAlchemy Declarative API; the DB column is still named "metadata".
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=UTC),
    )


# ---------------------------------------------------------------------------
# Internal helper — kept separate so tests can mock it cleanly
# ---------------------------------------------------------------------------


async def _insert_audit_row(
    session: AsyncSession,
    *,
    event: str,
    user_id: int | None,
    ip: str | None,
    outcome: str,
    metadata: dict[str, Any] | None,
    ts: datetime,
) -> None:
    """Insert one AuditLog row.  Exposed at module level for easy monkeypatching."""
    row = AuditLog(
        event=event,
        user_id=user_id,
        ip=ip,
        outcome=outcome,
        event_metadata=metadata,
        ts=ts,
    )
    session.add(row)
    # Use flush (not commit) so the caller controls the outer transaction boundary
    await session.flush()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def emit_audit_event(
    event: str,
    *,
    user_id: int | None = None,
    ip: str | None = None,
    outcome: str,
    session: AsyncSession | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Emit a structured audit event — always stdout, best-effort DB row.

    Args:
        event:    Event name from the taxonomy (login_success, budget_created, …).
        user_id:  Integer user PK.  Never pass email or username.
        ip:       Client IP address string.
        outcome:  "success" | "failure".
        session:  Async SQLAlchemy session for the DB write.  If None the DB
                  write is skipped (stdout only).
        metadata: Optional dict with resource IDs/types, HTTP status, token jti.
                  Must NOT contain PII.
    """
    now = datetime.now(tz=UTC)
    payload: dict[str, Any] = {
        "event": event,
        "user_id": user_id,
        "ip": ip,
        "outcome": outcome,
        "ts": now.isoformat(),
    }
    if metadata:
        payload["metadata"] = metadata

    # Always emit to stdout (structured JSON)
    _audit_logger.info(json.dumps(payload))

    # Best-effort DB write — never propagate failures
    if session is not None:
        try:
            await _insert_audit_row(
                session,
                event=event,
                user_id=user_id,
                ip=ip,
                outcome=outcome,
                metadata=metadata,
                ts=now,
            )
        except Exception:
            _audit_logger.warning(
                "audit DB write failed for event=%s user_id=%s — row not persisted",
                event,
                user_id,
            )
