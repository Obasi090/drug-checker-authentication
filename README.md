# Drug Checker SMS — Demonstration MVP

A local Flask and SQLite demonstration for deterministic lookups against a small Greenbook sample, with optional message parsing, image text extraction, and bounded Gemini explanations. The backend in `drug_checker/` remains the sole authority for registry, alert, and pack-comparison findings. A registry match does not authenticate a physical pack or establish safety. A missing record does not establish counterfeiting.

## MVP status

The checked-in `data/greenbook_sample.json` contains 80 entries: the original 20 Greenbook sample records and 60 explicitly synthetic `DEMO/SAMPLE` medicine examples. It is not the complete NAFDAC Greenbook, and the added examples do not represent real NAFDAC registrations. Synthetic alert fixtures are fictional demonstrations and are not NAFDAC notices. There is no authentic alert source checker or importer.

The mock SMS sender is for demonstrations and tests only; the project does not receive provider webhooks or send real SMS. This is a local demonstration MVP, not a public service.

## Architecture

- `drug_checker/` owns SQLite access, registry and alert tables, deterministic name/registration matching, packet-field comparisons, dataset status, and SMS reply formatting.
- `drug_checker/ai_integration.py` adapts selected optional capabilities from `drug_sms_checker_AI_ML/`. Its CSV catalogue, fuzzy verification pipeline, and independent findings are not used in backend decisions.
- `drug_checker/api.py` exposes health, text-check, packet-check, photo-extraction, and confirmed-photo-comparison routes.
- `drug_checker/import_greenbook.py` imports JSON records into the registry and supports a non-writing dry run.
- `drug_checker/seed_demo_alerts.py` explicitly and idempotently loads a synthetic alert fixture. Normal startup does not seed it.
- `data_import_runs` records source, source fetch time, local completion time, outcome, timestamp anomalies, and import counts. It does not make a partial dataset complete.

## Requirements

Python 3.10 or newer. Core runtime requirements are in `requirements.txt`; tests use `requirements-dev.txt`. Optional AI/OCR requirements are isolated in `requirements-ai.txt` and are not needed for deterministic backend lookups.

## Install

PowerShell:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

For optional message parsing, OCR, and Gemini support:

```powershell
python -m pip install -r requirements-ai.txt
```

Use a supported Python version already installed on the machine; the commands do not install Python itself. On macOS/Linux, activate `.venv` with `source .venv/bin/activate` and use `python -m pip` as above.

## Environment configuration

Copy `.env.example` as a reference, then set any values in the shell or deployment environment. The application does **not** automatically parse `.env` files.

- `DRUG_CHECKER_DB_PATH`: optional SQLite file path. Defaults to `drug_checker/drugs.db`, resolved from the package location rather than the current working directory. A relative override is resolved from the process working directory.
- `DRUG_CHECKER_LOG_PATH`: optional log file path. Defaults to `drug_checker/drug_db.log`.
- `ALLOWED_ORIGINS`: comma-separated browser origins allowed by the API. The default list is for local development only.
- `GEMINI_API_KEY`: optional Google GenAI key for explanation and extraction. Set it in the process environment; never commit or print it.
- `AI_ML_MOCK=1`: optional development setting for mocked Gemini behavior; it does not represent a live Gemini result.

Without optional dependencies or a Gemini key, the backend continues with deterministic parsing where possible and deterministic explanations. OCR may be unavailable.

## Database setup

Initialize an empty or existing database with the package initializer:

```powershell
python -m drug_checker.init_db
```

Initialization creates missing tables and indexes and applies additive metadata columns to `data_import_runs` and `source_kind` to `alerts`; it does not delete medicine or alert rows. For an existing database, make and verify a backup before applying schema changes. After importing the expanded demo JSON its registry source is identified as a sample; alert freshness remains unknown because there is no authentic alert source check.

## Greenbook import

The importer expects a JSON list in the existing Apify-export-shaped format, including fields such as `productId`, `registrationNumber`, `productName`, `status`, and optional `fetchedAt`. The repository's sample is not a complete source. Do not use it to represent complete registry coverage.

Preview a file without changing medicine rows or import history:

```powershell
python -m drug_checker.import_greenbook --dry-run path/to/greenbook-export.json
```

The dry run reports source fetch timestamp, total/valid/rejected rows, duplicate IDs, and expected inserts/updates/skips. Review the source provenance and completeness, then back up the target database before a real import:

```powershell
python -m drug_checker.import_greenbook path/to/validated-greenbook-export.json
```

Invalid source records stop the import before any medicine upserts and are recorded as an error attempt. Existing records absent from a source snapshot are not deleted. Import the included sample explicitly with:

```powershell
python -m drug_checker.import_greenbook --demo-sample data/greenbook_sample.json
```

The importer records its source as `NAFDAC Greenbook sample/demo dataset`. The file contains 80 entries, including 60 synthetic educational examples with fictional `DEMO-` identifiers. It is demo coverage only, not a complete registry; do not treat the fictional identifiers as real registrations.

## Regulatory alerts

Alert matching uses only records in SQLite's `alerts` table. The backend supports `recalled`, `suspended`, `withdrawn`, `cancelled`, and `warning`, and distinguishes registration-number matches from weaker name-only matches. There is no alert-source importer. An empty alert table without a successful source check reports `unknown`; synthetic fixtures do not change that status and are not an authentic source check. To load the fictional demo alert explicitly:

```powershell
python -m drug_checker.seed_demo_alerts
```

The fixture is marked `SYNTHETIC — DEMONSTRATION ONLY`, uses a reserved `.invalid` link, and is stored with `source_kind='synthetic'`. Normal app startup never loads it. Back up the database before removing synthetic rows later.

NAFDAC's public archive is at [nafdac.gov.ng/category/recalls-and-alerts](https://nafdac.gov.ng/category/recalls-and-alerts/). Its listings include varied product categories and notice types; importer design and coverage validation remain outstanding.

## Deployment preparation (Vercel + Render)

The repository includes static hosting configuration in `vercel.json` and a build script in `frontend/build.mjs`. Deploy the existing frontend files from `frontend/`; no frontend framework or package installation is required. In Vercel project settings, add the public (non-secret) build environment variable `DRUG_CHECKER_API_BASE_URL` with the HTTPS origin of the Render service, for example `https://your-service.onrender.com` (no trailing slash), then deploy. The build rejects non-HTTPS remote API URLs. The app uses `http://127.0.0.1:5000` only when opened locally and does not fall back to localhost on a public hostname.

`render.yaml`, `render_start.sh`, and `requirements-deploy.txt` prepare the existing Flask API for Render/Gunicorn. The free-plan SQLite path is `/tmp/drugs.db`, which is ephemeral. On a fresh instance, the launcher copies `data/deployment_seed.sqlite3` if the path does not exist, then runs the existing additive initializer. The seed contains 80 medicine rows, the existing 1 synthetic alert, import history, and passed SQLite integrity checks; it was created from a copy of the development database, which was not modified. Sample data is restored after an instance restart, but runtime database changes are lost. No import or alert seeding runs at normal startup.

Render deployment requires manually entering `ALLOWED_ORIGINS` as the exact deployed Vercel origin (for example `https://your-project.vercel.app`) and optionally `GEMINI_API_KEY` in Render's secret environment settings. The Gemini key remains server-side. Do not put it in Vercel or frontend configuration. Render Free services can spin down after 15 minutes without requests, and their filesystem is ephemeral; the app restores the fixed demo seed on startup, but does not preserve changes made to the database at runtime.

Manual setup sequence:

1. Push this repository to a Git provider, create a Vercel project from it, and deploy once to obtain the Vercel origin.
2. Create a Render Blueprint from the repository using the Free plan. Set `ALLOWED_ORIGINS` to the Vercel origin and optionally set `GEMINI_API_KEY` in Render's environment settings.
3. Wait for Render's `/api/health` check to pass and note the service HTTPS URL.
4. Set Vercel's `DRUG_CHECKER_API_BASE_URL` to that URL, redeploy, then check `/api/health` and perform a medicine lookup from the public frontend.
5. Treat the backend as a read-only demo: any runtime database changes are lost when its free instance restarts or spins down. The committed seed is copied again at startup.

For local serving, run the Flask API with `python -m drug_checker.api --host 127.0.0.1 --port 5000` and serve `frontend/` with a local static HTTP server. CORS is already controlled by `ALLOWED_ORIGINS`; for a separate local frontend origin, include that exact origin in the local backend environment. Do not use `file://` for browser integration because browsers restrict fetches from local files.

The frontend is deployed to Vercel. The backend deployment is pending Render account sign-in and service creation; the live frontend needs the backend URL configured after the API is available.

## Run the API

From the project root:

```powershell
python -m drug_checker.api
```

The default bind is `127.0.0.1:5000` with Flask debug disabled. To select another host or port:

```powershell
python -m drug_checker.api --host 127.0.0.1 --port 5000
```

### `GET /api/health`

Returns service health, registry row count and coverage scope, optional AI capability state, the trustworthy source date if known, and registry/alert freshness states.

```json
{
  "status": "ok",
  "drugs": 20,
  "data_as_of": "2026-11-19",
  "registry_data_status": {"status": "unknown"},
  "alert_data_status": {"status": "unknown"},
  "registry_scope": "sample_demo"
}
```

Status objects include source/timestamp and anomaly details when available. Import-count fields are null for historical runs that predate those fields.

### `POST /api/check`

Request JSON:

```json
{"message": "A4-1234"}
```

Request JSON may contain a medicine name/registration number or informal message, e.g. `{"message": "please check API Fixture Medicine"}`. The deterministic parser is tried first; optional extraction may suggest only text grounded in the user's message. Structured input is sent to the backend engine. The response contains authoritative `findings`, `sms_reply`, and a separate `explanation` object; explanations cannot change findings. Findings use `found`, `multiple`, `not_found`, or `invalid`; multiple candidates remain available for clarification. Sample coverage is identified in relevant responses.

### `POST /api/check-packet`

Request JSON contains user-confirmed text fields, such as:

```json
{"brand_name": "visible name", "reg_number": "A4-1234", "manufacturer": "visible maker", "strength": "visible strength"}
```

Returns deterministic registry findings and field mismatches. It compares submitted text and does not authenticate a physical package.

### `POST /api/photo/extract`

Multipart field `image` accepts supported PNG, JPEG, or WebP uploads up to 5 MiB. The image is processed in memory and not stored. The response contains visible OCR fields and `confirmed: false`; review and correct these fields first. OCR may require Gemini configuration and is never authentication.

### `POST /api/photo/compare`

JSON requires explicit `confirmed: true` and a `fields` object. Only confirmed or corrected fields are sent for backend comparison:

```json
{"confirmed": true, "fields": {"brand_name": "visible name", "registration_number": "A4-1234"}}
```

A copied registration number may match a registry record. Neither OCR nor registry matching proves a package genuine or safe.

Malformed JSON, missing fields, invalid values, oversized requests, unknown routes, and unexpected errors return JSON errors. The API currently has no authentication or rate limiting and should not be exposed publicly without those controls and an operational review.

## SMS interface

`drug_checker.sms_provider.SmsProvider` defines the outbound adapter contract. `MockSmsProvider` is in-memory and never sends a network request. Timeouts are returned as an uncertain delivery result to avoid automatic duplicate retries. No provider webhook, signature validation, provider-specific credentials, delivery callback, or real sender is implemented. Choose an SMS provider before implementing those pieces.

## Backups and restore

Before any production or development data import, stop writes and create a timestamped copy of the SQLite database. Verify the copy opens and run `PRAGMA integrity_check` on it. Restore only from a verified backup while the application is stopped; preserve the original file separately and verify row counts and integrity after restoration. This project does not automate backup rotation or restore operations.

## Tests

The backend/integration tests use temporary SQLite databases:

```powershell
python -m pytest tests -q
```

Focused optional Gemini/OCR package tests:

```powershell
python -m pytest drug_sms_checker_AI_ML/tests/test_gemini.py drug_sms_checker_AI_ML/tests/test_photo.py drug_sms_checker_AI_ML/tests/test_photo_api_errors.py -q
```

The full research package suite also includes fuzzy catalogue modules requiring RapidFuzz; those tests are outside production integration. Automated tests mock Gemini and never send SMS.

## Safety and known limitations

- Registry lookup is not physical-pack authentication and is not a safety determination.
- Not found is not proof of counterfeit status.
- Name-only alert matching is weaker than registration-number matching.
- Alert-data unknown is not evidence of no alerts.
- The current registry data is a small sample, not a complete Greenbook snapshot.
- Synthetic alerts are fictional fixtures, never NAFDAC notices. No authentic alert import/check exists; real alert status remains unknown.
- The mock SMS sender is not a real provider. There is no provider webhook or public deployment configuration.
- Gemini/OCR require optional dependencies and a user-supplied API key for live AI; OCR extracts visible text only and requires user review and confirmation.
- Do not use the service for diagnosis, dosing, treatment, drug interactions, pregnancy advice, or medication start/stop decisions. Direct safety concerns to NAFDAC or a qualified pharmacist.
