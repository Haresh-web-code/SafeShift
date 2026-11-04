# SafeShift

SafeShift is a workplace-safety assistant project for factory supervisors. It is being developed to help supervisors find relevant safety guidance in OSHA publications and, as the project grows, provide traceable answers with source citations and understandable response-time measurements.

## Problem

Factory supervisors need practical safety information while production and maintenance work is underway. Guidance is spread across long documents, while a generic answer may omit the source or fail to account for the site-specific procedure. SafeShift is intended to make source material easier to find without presenting itself as a substitute for approved workplace procedures or a qualified safety professional.

## Target users

Safety officers and factory supervisors, including supervisors supporting multiple production lines at a contract manufacturing site.

## Objectives

- Make OSHA safety publications easier to search and evaluate.
- Preserve document and PDF-page references for safety guidance.
- Build toward a responsive assistant with visible, measurable processing time.
- Clearly identify questions the available source material cannot answer.

## Dataset

The Week 1 evaluation set contains two OSHA publications and 116 PDF pages:

| Publication | Official source | Local sample | Pages |
|---|---|---|---:|
| OSHA 3120, *Control of Hazardous Energy (Lockout/Tagout)* | [OSHA PDF](https://www.osha.gov/sites/default/files/publications/osha3120.pdf) | `data/sample/OSHA3120_safeshift.pdf` | 45 |
| OSHA 3075, *Controlling Electrical Hazards* | [OSHA PDF](https://www.osha.gov/sites/default/files/publications/osha3075.pdf) | `data/sample/OSHA3075_safeshift.pdf` | 71 |

See [DATASET.md](DATASET.md) for collection notes and verification details. The evaluation questions and PDF-page references are in [docs/QUESTIONS.md](docs/QUESTIONS.md).

## Technology stack

- Python 3.12
- FastAPI and Uvicorn
- Pydantic Settings for application configuration
- Local OSHA PDF-page retrieval with document/page citations
- Google Gemini through the configurable `google-genai` SDK
- Pytest and HTTPX for automated API tests

The current retrieval implementation reads the generated `chunks.jsonl` file and ranks passages locally. PostgreSQL/pgvector is an optional Compose service for future work; it is not connected to the current retrieval path.

## Installation and environment

From the repository root, create and activate a virtual environment, then install the development dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

On macOS or Linux, use `python3 -m venv .venv` and `source .venv/bin/activate` instead.

Copy `.env.example` to `.env` and replace its placeholders. Set `GEMINI_API_KEY` and `GEMINI_MODEL` to credentials and a model enabled for your Google project. `GEMINI_FALLBACK_MODEL` is optional and must also be enabled. Timeouts, overall deadline, retry limit, optional input/output price rates, and local database name/user are configurable there. The optional database password is provided separately through `.secrets/postgres_password`. Never commit `.env`, `.secrets/`, or credentials; `.env.example` contains placeholders only.

## Run the application

```powershell
python -m uvicorn app.main:app --reload
```

The API is then available at `http://127.0.0.1:8000`.

Before using `/chat`, configure Gemini and create the retrieval index from the PDFs in `data/raw`:

```powershell
python ingest.py
```

Send a safety question to `POST /chat`:

```powershell
$body = @{ question = "What steps should I follow before servicing a conveyor belt?" } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/chat -Method Post -ContentType "application/json" -Body $body
```

The response includes the answer, OSHA document/page sources, AI status, and retrieval, generation, and total time in milliseconds. A 2-second response target is best-effort: the Gemini deadline is bounded, but a successful external response is not guaranteed. If retrieval is empty or Gemini is unavailable, `/chat` returns a structured safe response without inventing a procedure.

`POST /chat/stream` returns server-sent events. It emits source metadata before text, then a completion event with timings and usage. If streaming fails after text has been sent, it will not retry that stream; instead it marks the response partial and sends a warning.

`GET /usage` reports in-memory request, model, retry, and token totals for the current API process. The cost estimate is `null` unless both Gemini token rates are configured and generation usage metadata is available; estimates use the rates supplied in `.env`. Usage resets when the process restarts and is not persisted to PostgreSQL.

Run the API and optionally the standalone pgvector service with Docker Compose:

```powershell
docker compose up --build
```

The Docker image creates its local retrieval index from the tracked `data/sample` PDFs. To start the API together with the unused database service, put a strong password in `.secrets/postgres_password` and enable the `database` profile. The password file is ignored by Git and mounted as a Docker secret:

```powershell
docker compose --profile database up --build
```

The optional database service is not used by API retrieval.

## Deployment preparation

The existing Docker image is suitable for a small container deployment: it contains the FastAPI application, retrieval code, dependencies, and a `chunks.jsonl` index generated from the tracked `data/sample` PDFs during build. The image has a production startup command that honors the platform-provided `PORT` and a container health check against `/health`.

Google Cloud Run is a reasonable managed-container option for a small pilot because it can run the image without managing a server. Before deploying:

1. Build and publish the image to a container registry in your Google Cloud project.
2. Create a Cloud Run service from that image. Configure `GEMINI_API_KEY` using Secret Manager integration, not a checked-in file or a literal command-line value.
3. Configure `GEMINI_MODEL` to a model available to your project, and set operational values such as `GEMINI_TIMEOUT_MS`, `GEMINI_DEADLINE_MS`, and `GEMINI_MAX_RETRIES` through service environment settings.
4. Configure a startup/readiness check for `GET /health`. Keep the service private or add appropriate authentication/rate limiting before exposing it to the public; the API does not currently implement user authentication.
5. Confirm the deployed service can answer using the OSHA sample included in the image. No database is required for this retrieval implementation.

Cloud Run charges depend on region, request volume, CPU/memory, minimum instances, image storage/build, and outbound Gemini usage. Review current Google Cloud pricing and set budget alerts before enabling a paid service. Scale-to-zero can lower idle compute cost but introduces cold starts. `/usage` is process-local and in-memory, so it is not durable or an aggregate billing record. PostgreSQL/pgvector is not integrated into retrieval and should not be provisioned for the current API. No service has been deployed and no live URL is available.

### Health endpoint

Send a `GET` request to `http://127.0.0.1:8000/health`:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

The successful response is JSON with `status: "ok"` and the configured application name and environment. This liveness check does not call an LLM or database.

Run the tests with:

```powershell
$env:PYTHONPATH = "."
python -m pytest -q
```

## Current limitations

- Only two OSHA publications are in the Week 1 sample; chemical handling, machine guarding, confined spaces, and site-specific procedures are not covered comprehensively.
- The source documents are older publications. Consult current OSHA requirements, the employer's approved procedures, and qualified safety professionals for operational decisions.
- `/chat` grounds answers in the locally ingested OSHA documents. The available sample is not comprehensive and does not replace current requirements or site-specific procedures.
- The dataset cannot assess a particular workplace, predict an inspection result, or establish regulatory compliance.
- No live link is available because the application has not been deployed.

## Progress

**Week 1:** Foundation, health endpoint, 116-page OSHA sample dataset, and source-grounded evaluation questions are complete and locally verified. Repository registration on the course form and pushing the Week 1 tag require external confirmation/approval.

**Week 2:** The `/chat`, `/chat/stream`, `/health`, and `/usage` endpoints pass local tests (27 tests; Gemini is mocked). On 2026-11-04, the Docker image built and the API container became healthy; container `/health` and `/usage` calls and in-container OSHA retrieval succeeded. The database profile configuration parses, but the optional service was not started because `.secrets/postgres_password` is not present. A hosted CI run succeeded for repository commit `c28e9a2`; this checkout has uncommitted changes, so that run does not verify the current worktree. No deployment or release was performed; there is no live URL.
