# Local demo guide (Windows / Visual Studio 2026)

This guide runs the existing application locally. It does not deploy or publish anything. Start only the services needed for the demo you plan to show.

## Before you start

1. Open the backend and frontend folders in Visual Studio 2026 (or use two PowerShell terminals).
2. Confirm local configuration exists at `RiskManagementBackend\.env`. If it does not, copy `RiskManagementBackend\.env.example` to that path and fill in your own local values. Do not overwrite an existing `.env` and do not share or commit it.
3. Confirm PostgreSQL is running if you need the risk register or dashboard. In PowerShell:

   ```powershell
   Get-Service *postgres*
   ```

   Start the matching PostgreSQL service from Windows Services or an elevated PowerShell session if it is stopped. Use the database name and account in the backend `.env`. Do not reset or recreate an existing database for the demo.

4. AI analysis requires Ollama reachable at the configured `OLLAMA_BASE_URL`, signed in/configured for Cloud use, and the configured model available. ServiceNow synchronization requires valid backend OAuth settings and network access to the configured instance. Both are optional for demonstrating local risk CRUD and dashboard metrics.

## Start the backend

In a PowerShell terminal at `C:\VS2026Project\RiskManagementBackend`:

```powershell
.\RiskManagementBackend\.venv\Scripts\Activate.ps1
python RiskManagementBackend\run_api.py
```

If the virtual environment does not exist yet, create it and install dependencies first:

```powershell
py -m venv RiskManagementBackend\.venv
.\RiskManagementBackend\.venv\Scripts\Activate.ps1
python -m pip install -r RiskManagementBackend\requirements.txt
```

Expected API URL: `http://127.0.0.1:8000`  
Swagger UI: `http://127.0.0.1:8000/docs`

Check `http://127.0.0.1:8000/api/health` for `{"status":"ok"}`. In Swagger, use **Authorize** with the API username/password from the backend `.env`; do not paste or save credentials into project files. Then use the authenticated database health endpoint to check PostgreSQL.

## Start the frontend

Open a second PowerShell terminal at `C:\VS2026Project\RiskManagementFrontend\riskmanagementfrontend`:

```powershell
npm install
npm run dev -- --host 127.0.0.1
```

Vite is configured for port `60190`, so open `http://127.0.0.1:60190`. The backend CORS allowlist includes this local origin. If Vite reports that the port is already occupied, stop the other Vite process instead of using an alternate port that the backend does not allow.

Sign in using the backend `API_USERNAME` and `API_PASSWORD`. The frontend uses the backend at `http://127.0.0.1:8000` by default. An optional `VITE_API_BASE_URL` can change that URL, but it must point to an origin allowed by backend CORS.

## Demo checklist

1. **Local register and dashboard:** open the risk register; review existing records. Create or update a local risk to demonstrate validation and persistence. Avoid creating unnecessary records in a shared demo database.
2. **AI analysis (optional):** submit a synthetic scenario with no real sensitive data. Confirm Ollama is reachable and that the response indicates whether the analysis was live or simulated.
3. **ServiceNow (optional):** check backend `.env` points to the intended test/demo instance, then run the frontend's ServiceNow sync. The sync contacts that instance and refreshes the local synchronized snapshot. Do not edit or delete original ServiceNow records as part of this demo.
4. **Swagger (optional):** use authenticated endpoints at `/docs` to inspect the API. Avoid sending real secrets or sensitive risk details into test requests.

## Common issues

- **Backend cannot start / missing package:** activate the backend `.venv`, then run `python -m pip install -r RiskManagementBackend\requirements.txt`.
- **Database unavailable:** check the PostgreSQL Windows service, database name, host/port, and credentials in local `.env`; do not print credentials into support logs.
- **Browser cannot reach API / CORS error:** confirm backend is running on port 8000 and frontend is at port 60190. Stop an extra Vite instance if it selected a different port.
- **Sign-in fails:** use the current `API_USERNAME` and `API_PASSWORD` values from the backend `.env`. Avoid sharing them in screenshots or chat.
- **AI unavailable:** verify Ollama is running/reachable at `OLLAMA_BASE_URL` and the configured model is available to the account.
- **ServiceNow sync fails:** verify instance URL and OAuth client configuration in backend `.env`, instance API permissions, and network access. Error messages intentionally avoid showing credential values.

## Stop the demo

In each terminal, press `Ctrl+C` to stop Vite and FastAPI. Stop Ollama or PostgreSQL only if you started them specifically for this demo and no other application is using them. Keep the local `.env` and PostgreSQL data in place.
