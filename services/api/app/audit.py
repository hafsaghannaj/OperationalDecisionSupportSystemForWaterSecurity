from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from libs.schemas.risk import OperatorAuditLogEntry
from services.api.app.db_models import OperatorAuditLog
from services.api.app.time import format_week_string, parse_week_string


def record_audit_event(
    session: Session,
    *,
    action_type: str,
    target_type: str,
    target_id: str,
    operator_id: str | None = None,
    region_id: str | None = None,
    week: str | None = None,
    model_version: str | None = None,
    note: str | None = None,
    event_metadata: dict[str, Any] | None = None,
) -> OperatorAuditLog:
    record = OperatorAuditLog(
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        operator_id=operator_id,
        region_id=region_id,
        week_start_date=None if week is None else parse_week_string(week),
        model_version=model_version,
        note=note,
        event_metadata=event_metadata or {},
    )
    session.add(record)
    session.flush()
    return record


def build_audit_log_entry(record: OperatorAuditLog) -> OperatorAuditLogEntry:
    return OperatorAuditLogEntry(
        id=record.id,
        action_type=record.action_type,
        target_type=record.target_type,
        target_id=record.target_id,
        operator_id=record.operator_id,
        region_id=record.region_id,
        week=None if record.week_start_date is None else format_week_string(record.week_start_date),
        model_version=record.model_version,
        note=record.note,
        event_metadata=record.event_metadata or {},
        created_at=record.created_at.isoformat(),
    )


def list_audit_logs(
    session: Session,
    *,
    region_id: str | None = None,
    limit: int = 25,
) -> list[OperatorAuditLogEntry]:
    stmt = select(OperatorAuditLog).order_by(desc(OperatorAuditLog.created_at)).limit(limit)
    if region_id is not None:
        stmt = stmt.where(OperatorAuditLog.region_id == region_id)
    return [build_audit_log_entry(record) for record in session.scalars(stmt).all()]
