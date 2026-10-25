"""One-way import of ServiceNow IRM risks into the local PostgreSQL database."""

import json
import logging
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException

from database import get_db_connection

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api/v1/servicenow", tags=["ServiceNow IRM"])
TIMEOUT_SECONDS = 20
_cached_token: str | None = None
_token_expires_at = 0.0


def _configuration() -> tuple[str, str, str]:
    instance_url = os.getenv("SERVICENOW_INSTANCE_URL", "").rstrip("/")
    client_id = os.getenv("SERVICENOW_CLIENT_ID", "")
    client_secret = os.getenv("SERVICENOW_CLIENT_SECRET", "")
    missing = [name for name, value in (
        ("SERVICENOW_INSTANCE_URL", instance_url),
        ("SERVICENOW_CLIENT_ID", client_id),
        ("SERVICENOW_CLIENT_SECRET", client_secret),
    ) if not value]
    if missing:
        raise HTTPException(status_code=503, detail=f"ServiceNow integration is not configured. Set: {', '.join(missing)}.")
    if not instance_url.startswith("https://"):
        raise HTTPException(status_code=503, detail="SERVICENOW_INSTANCE_URL must use HTTPS.")
    return instance_url, client_id, client_secret


def _access_token(force_refresh: bool = False) -> str:
    global _cached_token, _token_expires_at
    if not force_refresh and _cached_token and time.monotonic() < _token_expires_at - 60:
        return _cached_token
    instance_url, client_id, client_secret = _configuration()
    payload = urlencode({"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}).encode()
    request = Request(f"{instance_url}/oauth_token.do", data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            token_response = json.loads(response.read().decode("utf-8"))
        token = token_response.get("access_token")
        if not isinstance(token, str) or not token:
            raise ValueError("missing access token")
        expires_in = int(token_response.get("expires_in", 1800))
    except HTTPError as error:
        logger.warning("ServiceNow OAuth request failed with HTTP %s", error.code)
        raise HTTPException(status_code=502 if error.code >= 500 else 503, detail="ServiceNow authentication failed. Check the OAuth client configuration and permissions.") from None
    except (URLError, TimeoutError, OSError):
        logger.warning("ServiceNow OAuth service could not be reached")
        raise HTTPException(status_code=504, detail="ServiceNow authentication timed out or could not be reached.") from None
    except (ValueError, json.JSONDecodeError, TypeError):
        logger.warning("ServiceNow OAuth returned an invalid response")
        raise HTTPException(status_code=502, detail="ServiceNow authentication returned an invalid response.") from None
    _cached_token = token
    _token_expires_at = time.monotonic() + max(expires_in, 60)
    return token


def _fetch_risks() -> list[dict]:
    instance_url, _, _ = _configuration()
    url = f"{instance_url}/api/now/table/sn_risk_risk?{urlencode({'sysparm_display_value': 'true', 'sysparm_limit': '10'})}"
    for attempt in range(2):
        request = Request(url, headers={"Authorization": f"Bearer {_access_token(force_refresh=attempt > 0)}", "Accept": "application/json"})
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode("utf-8"))
            records = body.get("result")
            if not isinstance(records, list):
                raise ValueError("missing result list")
            return records
        except HTTPError as error:
            if error.code == 401 and attempt == 0:
                continue
            logger.warning("ServiceNow risk retrieval failed with HTTP %s", error.code)
            raise HTTPException(status_code=502 if error.code >= 500 else 503, detail="ServiceNow risk retrieval failed. Check the IRM API permissions and try again.") from None
        except (URLError, TimeoutError, OSError):
            logger.warning("ServiceNow risk service could not be reached")
            raise HTTPException(status_code=504, detail="ServiceNow risk retrieval timed out or could not be reached.") from None
        except (ValueError, json.JSONDecodeError, TypeError):
            logger.warning("ServiceNow risk API returned an invalid response")
            raise HTTPException(status_code=502, detail="ServiceNow returned an invalid risk response.") from None
    raise HTTPException(status_code=503, detail="ServiceNow authentication failed. Please retry.")


def _display(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("display_value", value.get("value"))
    return str(value) if value is not None else None


@router.get("/risks")
def list_synced_risks() -> dict:
    """List the imported ServiceNow records for the Risk Register."""
    connection = None
    try:
        connection = get_db_connection()
        connection.execute("""CREATE TABLE IF NOT EXISTS servicenow_risks (
            sys_id TEXT PRIMARY KEY, number TEXT, name TEXT NOT NULL, description TEXT,
            score TEXT, state TEXT, category TEXT, synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        connection.commit()
        rows = connection.execute("""SELECT sys_id, number, name, description, score, state, category, synced_at
            FROM servicenow_risks ORDER BY number, name""").fetchall()
        return {"risks": [dict(row) for row in rows]}
    except Exception as error:
        logger.warning("Could not list synchronized ServiceNow risks (%s)", type(error).__name__)
        raise HTTPException(status_code=503, detail="Could not load synchronized risks. Check PostgreSQL availability.") from None
    finally:
        if connection is not None:
            connection.close()


@router.post("/sync")
def synchronize_risks() -> dict:
    """Fetch at most ten ServiceNow risks and idempotently upsert them locally."""
    records = _fetch_risks()
    connection = None
    imported = updated = skipped = 0
    try:
        connection = get_db_connection()
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
        for record in records:
            sys_id = _display(record.get("sys_id"))
            name = _display(record.get("name")) or _display(record.get("number"))
            if not sys_id or not name:
                skipped += 1
                continue
            params = (sys_id, _display(record.get("number")), name, _display(record.get("description")), _display(record.get("score")), _display(record.get("state")), _display(record.get("category")))
            existing = connection.execute("SELECT 1 FROM servicenow_risks WHERE sys_id = %s", (sys_id,)).fetchone()
            connection.execute("""INSERT INTO servicenow_risks (sys_id, number, name, description, score, state, category, synced_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (sys_id) DO UPDATE SET number = EXCLUDED.number, name = EXCLUDED.name,
                description = EXCLUDED.description, score = EXCLUDED.score, state = EXCLUDED.state,
                category = EXCLUDED.category, synced_at = NOW()""", params)
            if existing:
                updated += 1
            else:
                imported += 1
        connection.commit()
        return {"imported": imported, "updated": updated, "skipped": skipped, "total_received": len(records), "message": "ServiceNow risks synchronized successfully." if records else "ServiceNow returned no risk records."}
    except HTTPException:
        if connection is not None:
            connection.rollback()
        raise
    except Exception as error:
        if connection is not None:
            connection.rollback()
        logger.warning("ServiceNow risk synchronization failed (%s)", type(error).__name__)
        raise HTTPException(status_code=503, detail="Risk synchronization failed while saving to PostgreSQL.") from None
    finally:
        if connection is not None:
            connection.close()
