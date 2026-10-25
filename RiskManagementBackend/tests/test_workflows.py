import io
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from uuid import UUID

from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials
from pydantic import ValidationError
from starlette.requests import Request

import routers.ai as ai
import routers.risks as risks
import routers.servicenow as servicenow
from risk_scoring import calculate_risk_assessment
from schemas.ai import RiskAnalysisRequest
from schemas.risks import RiskInput, RiskRecord
from security import require_api_user


class Cursor:
    def __init__(self, row=None, rows=None): self.row, self.rows = row, rows or []
    def fetchone(self): return self.row
    def fetchall(self): return self.rows


class Connection:
    def __init__(self, result=None, local=None, external=None):
        self.result, self.local, self.external = result, local or [], external or []
        self.statements, self.committed = [], False
    def execute(self, query, params=None):
        self.statements.append((query, params))
        normalized = " ".join(query.lower().split())
        if "select * from local_risks" in normalized: return Cursor(rows=self.local)
        if "select sys_id, number, name" in normalized: return Cursor(rows=self.external)
        if "insert into local_risks" in normalized or "update local_risks" in normalized: return Cursor(row=self.result)
        return Cursor()
    def commit(self): self.committed = True
    def rollback(self): pass
    def close(self): pass


def sample_row(status="Open", score=12, severity="High"):
    now = datetime.now(timezone.utc)
    return {"id": UUID("c90d6d4d-3ca5-4a50-9a89-75ef10c7fd5b"), "title": "Payment processing interruption",
            "description": "A scheduled process may delay payment reconciliation.", "category": "Operational",
            "likelihood": 3, "impact": 4, "risk_score": score, "severity": severity,
            "status": status, "created_at": now, "updated_at": now}


class WorkflowTests(unittest.TestCase):
    def test_risk_and_ai_input_validation_and_score(self):
        payload = RiskInput(title="Payment risk", description="A sufficiently detailed risk description.", likelihood=3, impact=4)
        self.assertEqual(calculate_risk_assessment(payload.likelihood, payload.impact)["severity"], "High")
        with self.assertRaises(ValidationError): RiskInput(title="x", description="short", likelihood=6, impact=2)
        with self.assertRaises(ValidationError): RiskAnalysisRequest(description="too short")

    def test_auth_requires_correct_credentials_and_https_remotely(self):
        scope = {"type":"http", "method":"GET", "scheme":"https", "server":("risk.example",443), "client":("127.0.0.1",1), "headers":[(b"host",b"risk.example")], "path":"/", "root_path":"", "query_string":b""}
        good = HTTPBasicCredentials(username="operator", password="test-only-password")
        with patch.dict("os.environ", {"API_USERNAME":"operator", "API_PASSWORD":"test-only-password", "API_REQUIRE_HTTPS":"true"}):
            self.assertEqual(require_api_user(Request(scope), good), "operator")
            with self.assertRaises(HTTPException) as missing: require_api_user(Request(scope), None)
            self.assertEqual(missing.exception.status_code, 401)
            with self.assertRaises(HTTPException) as insecure: require_api_user(Request({**scope,"scheme":"http"}), good)
            self.assertEqual(insecure.exception.status_code, 400)

    def test_create_and_update_recalculate_scores_and_persist(self):
        row = sample_row()
        payload = RiskInput(title=row["title"], description=row["description"], category="Operational", likelihood=3, impact=4)
        connection = Connection(result=row)
        with patch.object(risks, "get_db_connection", return_value=connection): result = risks.create_risk(payload)
        self.assertEqual((result["risk_score"], result["severity"]), (12,"High"))
        self.assertTrue(connection.committed)
        self.assertEqual(RiskRecord.model_validate(result).status, "Open")

        updated = {**row, "risk_score":20, "severity":"Critical", "status":"Closed"}
        connection = Connection(result=updated)
        payload = RiskInput(title=row["title"], description=row["description"], category="Operational", likelihood=4, impact=5, status="Closed")
        with patch.object(risks, "get_db_connection", return_value=connection): result = risks.update_risk(row["id"], payload)
        self.assertEqual((result["risk_score"], result["severity"], result["status"]), (20,"Critical","Closed"))
        self.assertIn("WHERE id = %s RETURNING *", connection.statements[-1][0])

    def test_dashboard_metrics_aggregate_both_sources(self):
        local = sample_row()
        external = {"sys_id":"stable-id", "number":"RK123", "name":"Imported risk", "description":"Source record.", "score":"4 - High", "state":"Draft", "category":"Financial", "synced_at":datetime.now(timezone.utc)}
        connection = Connection(local=[local], external=[external])
        with patch.object(risks, "get_db_connection", return_value=connection): result = risks.risk_metrics()
        self.assertEqual((result["total"],result["local"],result["servicenow"],result["critical"]),(2,1,1,0))
        self.assertEqual(result["severity_counts"]["High"],2)

    def test_ai_transport_and_malformed_output_errors(self):
        with patch.object(ai, "urlopen", side_effect=URLError("private test detail")):
            with self.assertRaises(HTTPException) as unavailable: ai._request_ollama("synthetic")
        self.assertEqual(unavailable.exception.status_code,503)
        with patch.object(ai, "urlopen", return_value=io.BytesIO(b'{"message":{"content":"not-json"}}')):
            with self.assertRaises(HTTPException) as malformed: ai._request_ollama("synthetic")
        self.assertEqual(malformed.exception.status_code,502)

    def test_servicenow_refreshes_expired_token_and_accepts_empty_list(self):
        servicenow._cached_token, servicenow._token_expires_at = None, 0
        responses = [io.BytesIO(b'{"access_token":"old","expires_in":1800}'), HTTPError("https://example.invalid/table",401,"Unauthorized",{},None), io.BytesIO(b'{"access_token":"new","expires_in":1800}'), io.BytesIO(b'{"result":[]}')]
        with patch.object(servicenow, "_configuration", return_value=("https://example.invalid","id","secret")), patch.object(servicenow, "urlopen", side_effect=responses) as opened:
            self.assertEqual(servicenow._fetch_risks(), [])
        self.assertEqual(opened.call_count,4)
        self.assertIn("sysparm_limit=10",opened.call_args_list[-1].args[0].full_url)

    def test_incomplete_service_record_is_skipped(self):
        connection = Connection()
        records = [{"name":"missing stable identifier"}, {"sys_id":"test-only-id", "name":"valid test risk"}]
        with patch.object(servicenow, "_fetch_risks", return_value=records), patch.object(servicenow, "get_db_connection", return_value=connection):
            result = servicenow.synchronize_risks()
        self.assertEqual((result["imported"], result["skipped"], result["total_received"]), (1,1,2))

    def test_database_failure_returns_safe_error(self):
        payload = RiskInput(title="Payment risk", description="A sufficiently detailed risk description.", likelihood=3, impact=4)
        with patch.object(risks, "get_db_connection", side_effect=RuntimeError("private connection detail")):
            with self.assertRaises(HTTPException) as failure: risks.create_risk(payload)
        self.assertEqual(failure.exception.status_code,503)
        self.assertNotIn("private",failure.exception.detail)


if __name__ == "__main__": unittest.main()
