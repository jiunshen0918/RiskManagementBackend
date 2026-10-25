"""Single-operator HTTP Basic authentication for the local API."""

import hmac
import os

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

_basic_auth = HTTPBasic(auto_error=False, realm="Risk Management API")
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}


def require_api_user(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(_basic_auth),
) -> str:
    """Require configured operator credentials and HTTPS outside loopback."""
    expected_username = os.getenv("API_USERNAME", "")
    expected_password = os.getenv("API_PASSWORD", "")
    if not expected_username or not expected_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured. Set API_USERNAME and API_PASSWORD.",
        )

    host = (request.url.hostname or "").lower()
    require_https = os.getenv("API_REQUIRE_HTTPS", "true").lower() not in {"0", "false", "no"}
    if require_https and host not in _LOOPBACK_HOSTS and request.url.scheme != "https":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HTTPS is required for authenticated API requests.",
        )

    if credentials is None or not (
        hmac.compare_digest(credentials.username.encode("utf-8"), expected_username.encode("utf-8"))
        and hmac.compare_digest(credentials.password.encode("utf-8"), expected_password.encode("utf-8"))
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API credentials.",
            headers={"WWW-Authenticate": 'Basic realm="Risk Management API"'},
        )
    return credentials.username
