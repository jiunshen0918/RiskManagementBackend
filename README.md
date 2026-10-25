# AI-Powered Risk Management System — Backend

FastAPI backend for the [AI-Powered Risk Management System frontend](https://github.com/jiunshen0918/RiskManagementFrontend). The application supports a local risk register, persisted ServiceNow IRM risk snapshots, database-backed dashboard metrics, AI risk analysis, and authenticated API access.

## Features

- Authenticated FastAPI endpoints for local risks, AI analysis, and ServiceNow synchronization.
- PostgreSQL persistence using `psycopg` and parameterized SQL. The project does not use SQLAlchemy.
- Likelihood × impact scoring for local risks and dashboard aggregates calculated from persisted local and ServiceNow data.
- Ollama-compatible AI analysis and ServiceNow OAuth/API integration, configured on the backend only.
- Input validation and a standard-library `unittest` workflow suite.

## Architecture and data flow

```text
React frontend → FastAPI backend → PostgreSQL
                                → Ollama Cloud (AI analysis)
                                → ServiceNow IRM (risk synchronization)
```

The browser sends API requests to FastAPI. FastAPI authenticates requests, persists local risks and synchronized ServiceNow records in PostgreSQL, and makes outbound AI or ServiceNow calls using backend environment configuration. ServiceNow records are presented read-only in the frontend; locally managed risk records can be created and updated.

## Repository layout

```text
RiskManagementBackend/
├── README.md
├── LOCAL_DEMO.md
└── RiskManagementBackend/
    ├── main.py                 # FastAPI app, CORS, health endpoints
    ├── run_api.py              # Local Visual Studio / Uvicorn entry point
    ├── database.py             # PostgreSQL connection and schema setup
    ├── security.py             # API authentication
    ├── risk_scoring.py         # Local risk scoring
    ├── routers/                # AI, risks, and ServiceNow routes
    ├── schemas/                # Request and response validation
    ├── tests/                  # Automated workflow tests
    ├── requirements.txt
    ├── .env.example            # Placeholder configuration only
    └── .gitignore
```

## Requirements

- Windows 10/11 and Python 3.11 or newer.
- PostgreSQL running locally for persisted risk data and database health checks.
- Ollama configured for Cloud access and the selected model for live AI analysis.
- A ServiceNow IRM instance and OAuth client for synchronization. These integrations are optional for a basic API/frontend startup, but required to demonstrate those functions.
- Node.js/npm for the separate frontend repository.

## Setup

Open PowerShell in the backend repository root (`C:\VS2026Project\RiskManagementBackend`). Create and activate a virtual environment if one is not already present:

```powershell
py -m venv RiskManagementBackend\.venv
.\RiskManagementBackend\.venv\Scripts\Activate.ps1
python -m pip install -r RiskManagementBackend\requirements.txt
```

Create `RiskManagementBackend\.env` from `RiskManagementBackend\.env.example` only if you do not already have a local `.env`. Edit the local file with your own values; never commit it. The example uses placeholders.

### PostgreSQL

Create a local database named `risk_management_db` (or set `DB_NAME` to an existing database). Set `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` in the backend `.env`. The application initializes its required tables when it connects. The database account needs permission to create/use those tables.

### Ollama Cloud

Set `OLLAMA_BASE_URL` to the Ollama endpoint reachable from the backend and `OLLAMA_MODEL` to a model available to your Ollama account. The sample defaults to the local Ollama API at `http://localhost:11434` and `gpt-oss:20b-cloud`; configure/sign in to Ollama separately as required. Keep any Ollama access credential on the backend. AI analysis is unavailable if Ollama cannot be reached.

### ServiceNow IRM

Set `SERVICENOW_INSTANCE_URL`, `SERVICENOW_CLIENT_ID`, and `SERVICENOW_CLIENT_SECRET` in the backend `.env`, using the OAuth client configured for your instance. Keep client credentials on the backend. Sync calls contact the configured instance and update the application's local synchronized records; confirm the instance configuration before running a demo sync.

### API authentication

Set a unique `API_USERNAME` and a long random `API_PASSWORD` in the backend `.env`. `API_REQUIRE_HTTPS=true` enforces HTTPS for non-loopback requests; loopback local development is permitted over HTTP. Frontend API credentials are entered at runtime and held in browser memory for that session. Never put ServiceNow or Ollama credentials in frontend configuration.

## Run locally

From the backend repository root, with the virtual environment active and `.env` configured:

```powershell
python RiskManagementBackend\run_api.py
```

The API listens on `http://127.0.0.1:8000`. The interactive Swagger UI is at `http://127.0.0.1:8000/docs`; use the configured API username/password with its Authorize control. `/` and `/api/health` provide unauthenticated process checks. Database checks and application data endpoints require authentication.

For the complete beginner-friendly order, Visual Studio setup, smoke checks, troubleshooting, and stop instructions, see [LOCAL_DEMO.md](LOCAL_DEMO.md).

## Tests and checks

From the backend repository root with its virtual environment active:

```powershell
python -m unittest discover -s RiskManagementBackend\tests -v
python -m compileall -q RiskManagementBackend
python -m pip check
```

The unit suite mocks database and outbound service boundaries; it does not replace live PostgreSQL, Ollama, or ServiceNow integration checks.

## Security and known limitations

- `.env` and `.env.*` are ignored while `.env.example` is explicitly allowed. Verify with `git check-ignore -v RiskManagementBackend/.env` before staging. Ignore rules do not untrack files already committed.
- API Basic authentication is for a single operator; this is not a multi-user identity/role system and has no rate limiting. Do not expose the local development server publicly.
- HTTPS is required for non-loopback requests when `API_REQUIRE_HTTPS=true`; use a properly configured HTTPS reverse proxy for any later hosted deployment.
- ServiceNow records are read-only in the UI and there is no local risk deletion workflow.
- AI availability and output depend on the configured Ollama service/model. Automated tests use mocked external calls.
- Review repository history and rotate any credential if one was ever committed; adding `.gitignore` does not erase Git history.

## Related repository

- Frontend: [RiskManagementFrontend](https://github.com/jiunshen0918/RiskManagementFrontend)
