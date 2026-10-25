from logging import getLogger

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from database import get_db_connection
from routers.ai import router as ai_router
from routers.servicenow import router as servicenow_router
from routers.risks import router as risks_router
from security import require_api_user

logger = getLogger("uvicorn.error")

app = FastAPI(
    title="AI-Powered Risk Management API",
    description="API for the Risk Management System portfolio project.",
    version="0.1.0",
)

app.include_router(ai_router)
app.include_router(servicenow_router)
app.include_router(risks_router)

# Vite normally uses port 5173. This project currently uses port 60190.
allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:60190",
    "http://127.0.0.1:60190",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/")
def read_root() -> dict[str, str]:
    """Return a welcome message so the root URL is easy to check."""
    return {"message": "Risk Management API is running"}


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Check that the FastAPI process is responding."""
    return {"status": "ok"}


@app.get("/api/health/database", dependencies=[Depends(require_api_user)])
def database_health_check() -> dict[str, str]:
    """Check PostgreSQL without returning connection details or credentials."""
    connection = None
    try:
        connection = get_db_connection()
        connection.execute("SELECT 1").fetchone()
        return {"status": "ok", "database": "connected"}
    except Exception as error:
        # Log only the exception type; connection strings and secrets stay private.
        logger.warning("Database health check failed (%s)", type(error).__name__)
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Check the local database configuration and PostgreSQL service.",
        ) from None
    finally:
        if connection is not None:
            connection.close()


@app.get("/api/v1/auth/check", dependencies=[Depends(require_api_user)])
def auth_check() -> dict[str, bool]:
    """Confirm the supplied API credentials are valid."""
    return {"authenticated": True}
