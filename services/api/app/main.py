import re
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from libs.pilot import load_demo_risk_points, load_pilot_definition
from outbreaks.cag.api import router as cag_router
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from services.api.app.audit import build_audit_log_entry, list_audit_logs, record_audit_event
from services.api.app.config import get_settings
from services.api.app.db import get_db_session
from services.api.app.model_registry import load_model_comparison, promote_model_run as promote_registered_model_run
from services.api.app.model_status import load_model_card, load_model_status
from services.api.app.models import (
    AlertEvent,
    AlertResolveResponse,
    DataQualityRow,
    DemoRiskPoint,
    DriverBreakdown,
    FieldActionCreateRequest,
    ModelCardDocument,
    ModelComparison,
    ModelPromotionResponse,
    ModelStatus,
    OperatorActionRequest,
    OperatorAuditLogEntry,
    PilotDefinition,
    RegionSummary,
    RiskAllWeeksRow,
    RiskHistoryPoint,
    RiskSnapshot,
    ScoringHealth,
)
from services.api.app.repositories import (
    acknowledge_alert,
    get_driver_breakdown,
    get_regions_geojson,
    get_risk_history,
    list_alerts,
    list_all_risk,
    list_data_quality,
    list_latest_risk,
    list_regions,
    resolve_alert,
)
from services.api.app.scoring_runs import load_scoring_health
from services.api.app.time import parse_week_string

settings = get_settings()
DbSession = Annotated[Session, Depends(get_db_session)]

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

_REGION_ID_RE = re.compile(r"^[A-Z]{2}-\d{2,6}$")

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _require_api_key(api_key: str | None = Security(_api_key_header)) -> None:
    """Enforce API key on write endpoints when ODSSWS_API_KEY is configured."""
    s = get_settings()
    if s.api_key and api_key != s.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def _validate_region_id(region_id: str) -> str:
    if not _REGION_ID_RE.match(region_id):
        raise HTTPException(status_code=422, detail="Invalid region_id format.")
    return region_id


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Operational decision support API for OperationalDecisionSupportSystemForWaterSecurity.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)
app.include_router(cag_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/pilot", response_model=PilotDefinition)
def pilot_definition() -> PilotDefinition:
    return PilotDefinition(**load_pilot_definition())


@app.get("/demo/risk-points", response_model=list[DemoRiskPoint])
def demo_risk_points() -> list[DemoRiskPoint]:
    return [DemoRiskPoint(**row) for row in load_demo_risk_points()]


@app.get("/audit/logs", response_model=list[OperatorAuditLogEntry])
def audit_logs(
    session: DbSession,
    region_id: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
) -> list[OperatorAuditLogEntry]:
    try:
        return list_audit_logs(session, region_id=region_id, limit=limit)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Audit log unavailable.") from exc


@app.get("/model/status", response_model=ModelStatus)
def model_status() -> ModelStatus:
    try:
        return load_model_status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Model metadata unavailable.") from exc


@app.get("/model/card", response_model=ModelCardDocument)
def model_card() -> ModelCardDocument:
    try:
        card = load_model_card()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Model card unavailable.") from exc

    if card is None:
        raise HTTPException(status_code=404, detail="No promoted model card found.")
    return card


@app.get("/model/compare", response_model=ModelComparison)
def model_compare(session: DbSession) -> ModelComparison:
    try:
        return load_model_comparison(session)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Model registry unavailable.") from exc


@app.post("/model/runs/{model_version}/promote", response_model=ModelPromotionResponse)
def promote_model_run_endpoint(
    session: DbSession,
    model_version: str,
    payload: OperatorActionRequest | None = None,
    _auth: None = Depends(_require_api_key),
) -> ModelPromotionResponse:
    try:
        response = promote_registered_model_run(session, model_version)
        record_audit_event(
            session,
            action_type="model_promoted",
            target_type="model_run",
            target_id=model_version,
            operator_id=None if payload is None else payload.operator_id,
            model_version=model_version,
            note=None if payload is None else payload.note,
            event_metadata={
                "status": response.status,
                "previous_active_model_version": response.previous_active_model_version,
            },
        )
        session.commit()
        return response
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Model registry unavailable.") from exc


@app.get("/scoring/health", response_model=ScoringHealth)
def scoring_health(session: DbSession) -> ScoringHealth:
    try:
        return load_scoring_health(session)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Scoring run registry unavailable.") from exc


@app.get("/regions", response_model=list[RegionSummary])
def list_regions_endpoint(session: DbSession) -> list[RegionSummary]:
    try:
        return list_regions(session)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable for region lookup.") from exc


@app.get("/risk/latest", response_model=list[RiskSnapshot])
def latest_risk(session: DbSession) -> list[RiskSnapshot]:
    try:
        return list_latest_risk(session)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable for risk lookup.") from exc


@app.get("/risk/history", response_model=list[RiskHistoryPoint])
def risk_history(
    session: DbSession,
    region_id: str = Query(..., description="Administrative region identifier"),
) -> list[RiskHistoryPoint]:
    region_id = _validate_region_id(region_id)
    try:
        history = get_risk_history(session, region_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable for risk history lookup.") from exc

    if not history:
        raise HTTPException(status_code=404, detail=f"No risk history found for region '{region_id}'.")
    return history


@app.get("/drivers/{region_id}/{week}", response_model=DriverBreakdown)
def drivers(session: DbSession, region_id: str, week: str) -> DriverBreakdown:
    region_id = _validate_region_id(region_id)
    try:
        parse_week_string(week)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        breakdown = get_driver_breakdown(session, region_id, week)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable for driver lookup.") from exc

    if breakdown is None:
        raise HTTPException(status_code=404, detail="Driver breakdown not found.")
    return breakdown


@app.get("/alerts", response_model=list[AlertEvent])
def alerts(session: DbSession) -> list[AlertEvent]:
    try:
        return list_alerts(session)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable for alert lookup.") from exc


@app.get("/regions/geojson")
def regions_geojson(session: DbSession) -> dict:
    try:
        return get_regions_geojson(session)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable for GeoJSON lookup.") from exc


@app.patch("/alerts/{region_id}/{week}/resolve", response_model=AlertResolveResponse)
def resolve_alert_endpoint(
    session: DbSession,
    region_id: str,
    week: str,
    payload: OperatorActionRequest | None = None,
    _auth: None = Depends(_require_api_key),
) -> AlertResolveResponse:
    region_id = _validate_region_id(region_id)
    try:
        parse_week_string(week)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        found = resolve_alert(session, region_id, week)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable.") from exc
    if not found:
        raise HTTPException(status_code=404, detail="Alert not found.")
    record_audit_event(
        session,
        action_type="alert_resolved",
        target_type="alert_event",
        target_id=f"{region_id}:{week}",
        operator_id=None if payload is None else payload.operator_id,
        region_id=region_id,
        week=week,
        note=None if payload is None else payload.note,
        event_metadata={"status": "resolved"},
    )
    session.commit()
    return AlertResolveResponse(
        region_id=region_id, week=week, status="resolved",
        message="Alert has been marked as resolved."
    )


@app.post("/alerts/{region_id}/{week}/acknowledge", response_model=AlertResolveResponse)
def acknowledge_alert_endpoint(
    session: DbSession,
    region_id: str,
    week: str,
    payload: OperatorActionRequest | None = None,
    _auth: None = Depends(_require_api_key),
) -> AlertResolveResponse:
    region_id = _validate_region_id(region_id)
    try:
        parse_week_string(week)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        found = acknowledge_alert(session, region_id, week)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable.") from exc
    if not found:
        raise HTTPException(status_code=404, detail="Alert not found.")
    record_audit_event(
        session,
        action_type="alert_acknowledged",
        target_type="alert_event",
        target_id=f"{region_id}:{week}",
        operator_id=None if payload is None else payload.operator_id,
        region_id=region_id,
        week=week,
        note=None if payload is None else payload.note,
        event_metadata={"status": "acknowledged"},
    )
    session.commit()
    return AlertResolveResponse(
        region_id=region_id,
        week=week,
        status="acknowledged",
        message="Alert has been acknowledged for operator review.",
    )


@app.post("/field-actions", response_model=OperatorAuditLogEntry)
def create_field_action(
    session: DbSession,
    payload: FieldActionCreateRequest,
    _auth: None = Depends(_require_api_key),
) -> OperatorAuditLogEntry:
    region_id = _validate_region_id(payload.region_id)
    try:
        parse_week_string(payload.week)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        record = record_audit_event(
            session,
            action_type="field_action_noted",
            target_type="field_action",
            target_id=f"{region_id}:{payload.week}:{payload.action}",
            operator_id=payload.operator_id,
            region_id=region_id,
            week=payload.week,
            note=payload.note,
            event_metadata={"action": payload.action},
        )
        session.commit()
        session.refresh(record)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable.") from exc

    return build_audit_log_entry(record)


@app.get("/risk/all-weeks", response_model=list[RiskAllWeeksRow])
def all_weeks_risk(session: DbSession) -> list[RiskAllWeeksRow]:
    try:
        rows = list_all_risk(session)
        return [RiskAllWeeksRow(**row) for row in rows]
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable.") from exc


@app.get("/data/quality", response_model=list[DataQualityRow])
def data_quality(session: DbSession) -> list[DataQualityRow]:
    try:
        rows = list_data_quality(session)
        return [DataQualityRow(**row) for row in rows]
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable.") from exc
