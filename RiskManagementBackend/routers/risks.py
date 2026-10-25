"""Local risk CRUD and read-only metrics across local and ServiceNow risks."""

import logging
from collections import Counter
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from database import get_db_connection
from risk_scoring import calculate_risk_assessment
from schemas.risks import RiskInput, RiskRecord
from security import require_api_user

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api/v1/risks", tags=["Risk Management"], dependencies=[Depends(require_api_user)])


def _ensure_tables(connection) -> None:
    """Create application tables in place without altering existing records."""
    connection.execute("""CREATE TABLE IF NOT EXISTS local_risks (
        id UUID PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        category TEXT,
        likelihood SMALLINT NOT NULL CHECK (likelihood BETWEEN 1 AND 5),
        impact SMALLINT NOT NULL CHECK (impact BETWEEN 1 AND 5),
        risk_score SMALLINT NOT NULL CHECK (risk_score BETWEEN 1 AND 25),
        severity TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('Open', 'In Progress', 'Closed')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS servicenow_risks (
        sys_id TEXT PRIMARY KEY,
        number TEXT,
        name TEXT NOT NULL,
        description TEXT,
        score TEXT,
        state TEXT,
        category TEXT,
        synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    connection.commit()


def _external_severity(score: str | None) -> str:
    value = (score or "").casefold()
    if "critical" in value or "very high" in value:
        return "Critical"
    if "high" in value:
        return "High"
    if "moderate" in value or "medium" in value:
        return "Medium"
    if "low" in value:
        return "Low"
    return "Unknown"


def _local_record(row: dict) -> dict:
    return {
        "id": str(row["id"]), "sys_id": None, "number": None,
        "title": row["title"], "description": row["description"],
        "category": row["category"], "score": str(row["risk_score"]),
        "risk_score": row["risk_score"], "severity": row["severity"],
        "likelihood": row["likelihood"], "impact": row["impact"],
        "status": row["status"], "source": "Local",
        "updated_at": row["updated_at"].isoformat(),
        "created_at": row["created_at"].isoformat(),
    }


def _service_record(row: dict) -> dict:
    return {
        "id": None, "sys_id": row["sys_id"], "number": row["number"],
        "title": row["name"], "description": row["description"],
        "category": row["category"], "score": row["score"],
        "risk_score": None, "severity": _external_severity(row["score"]),
        "likelihood": None, "impact": None,
        "status": row["state"] or "Unknown", "source": "ServiceNow",
        "updated_at": row["synced_at"].isoformat(),
        "created_at": row["synced_at"].isoformat(),
    }


def _assessment(likelihood: int, impact: int) -> dict:
    try:
        return calculate_risk_assessment(likelihood, impact)
    except RuntimeError:
        logger.error("Risk score thresholds are invalid")
        raise HTTPException(status_code=500, detail="Risk scoring is not configured correctly.") from None


def _read_risks() -> list[dict]:
    connection = None
    try:
        connection = get_db_connection()
        _ensure_tables(connection)
        local = connection.execute("SELECT * FROM local_risks ORDER BY updated_at DESC").fetchall()
        external = connection.execute("""SELECT sys_id, number, name, description, score, state,
            category, synced_at FROM servicenow_risks""").fetchall()
        results = [_local_record(dict(row)) for row in local]
        results.extend(_service_record(dict(row)) for row in external)
        results.sort(key=lambda risk: risk["updated_at"], reverse=True)
        return results
    except Exception as error:
        logger.warning("Could not read risk records (%s)", type(error).__name__)
        raise HTTPException(status_code=503, detail="Could not load risks. Check PostgreSQL availability.") from None
    finally:
        if connection is not None:
            connection.close()


@router.get("")
def list_risks() -> dict:
    """Return local and imported risks together, with source clearly identified."""
    return {"risks": _read_risks()}


@router.post("", response_model=RiskRecord, status_code=status.HTTP_201_CREATED)
def create_risk(payload: RiskInput) -> dict:
    assessment = _assessment(payload.likelihood, payload.impact)
    connection = None
    try:
        connection = get_db_connection()
        _ensure_tables(connection)
        row = connection.execute("""INSERT INTO local_risks
            (id, title, description, category, likelihood, impact, risk_score, severity, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (uuid4(), payload.title, payload.description, payload.category, payload.likelihood,
             payload.impact, assessment["risk_score"], assessment["severity"], payload.status)).fetchone()
        connection.commit()
        result = _local_record(dict(row))
        return {**result, "id": result["id"]}
    except Exception as error:
        if connection is not None:
            connection.rollback()
        logger.warning("Risk creation failed (%s)", type(error).__name__)
        raise HTTPException(status_code=503, detail="Could not save the risk to PostgreSQL.") from None
    finally:
        if connection is not None:
            connection.close()


@router.put("/{risk_id}", response_model=RiskRecord)
def update_risk(risk_id: UUID, payload: RiskInput) -> dict:
    assessment = _assessment(payload.likelihood, payload.impact)
    connection = None
    try:
        connection = get_db_connection()
        _ensure_tables(connection)
        row = connection.execute("""UPDATE local_risks SET title = %s, description = %s,
            category = %s, likelihood = %s, impact = %s, risk_score = %s, severity = %s,
            status = %s, updated_at = NOW() WHERE id = %s RETURNING *""",
            (payload.title, payload.description, payload.category, payload.likelihood,
             payload.impact, assessment["risk_score"], assessment["severity"],
             payload.status, risk_id)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Local risk not found.")
        connection.commit()
        return _local_record(dict(row))
    except HTTPException:
        if connection is not None:
            connection.rollback()
        raise
    except Exception as error:
        if connection is not None:
            connection.rollback()
        logger.warning("Risk update failed (%s)", type(error).__name__)
        raise HTTPException(status_code=503, detail="Could not update the risk in PostgreSQL.") from None
    finally:
        if connection is not None:
            connection.close()


@router.get("/metrics")
def risk_metrics() -> dict:
    """Calculate dashboard counts and recent risks from persisted records."""
    risks = _read_risks()
    severity_counts = Counter(risk["severity"] for risk in risks)
    status_counts = Counter(risk["status"] for risk in risks)
    closed_statuses = {"closed", "retired", "cancelled", "canceled"}
    return {
        "total": len(risks),
        "critical": severity_counts["Critical"],
        "open": sum(risk["status"].casefold() not in closed_statuses for risk in risks),
        "local": sum(risk["source"] == "Local" for risk in risks),
        "servicenow": sum(risk["source"] == "ServiceNow" for risk in risks),
        "severity_counts": dict(severity_counts),
        "status_counts": dict(status_counts),
        "recent_risks": risks[:5],
    }
