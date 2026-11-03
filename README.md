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
- Pytest and HTTPX for automated API tests

Week 1 provides the health endpoint and dataset/documentation baseline. It does not yet expose a question-answering API, vector database, or deployed service.

## Installation and environment

From the repository root, create and activate a virtual environment, then install the development dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

On macOS or Linux, use `python3 -m venv .venv` and `source .venv/bin/activate` instead.

The Week 1 health endpoint needs no API key or `.env` file. Optional settings can be supplied through environment variables or a local `.env` file; never commit `.env` or credentials. `.env.example` contains placeholders only.

## Run the application

```powershell
python -m uvicorn app.main:app --reload
```

The API is then available at `http://127.0.0.1:8000`.

### Health endpoint

Send a `GET` request to `http://127.0.0.1:8000/health`:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

The successful response is JSON with `status: "ok"` and the configured application name and environment. This liveness check does not call an LLM or database.

Run the Week 1 tests with:

```powershell
$env:PYTHONPATH = "."
python -m pytest -q
```

## Current limitations

- Only two OSHA publications are in the Week 1 sample; chemical handling, machine guarding, confined spaces, and site-specific procedures are not covered comprehensively.
- The source documents are older publications. Consult current OSHA requirements, the employer's approved procedures, and qualified safety professionals for operational decisions.
- The application currently exposes only `/health`; there is no production question-answering endpoint or deployed service.
- The dataset cannot assess a particular workplace, predict an inspection result, or establish regulatory compliance.
- No live link is available because the application has not been deployed.

## Progress

**Week 1:** Foundation, health endpoint, 116-page OSHA sample dataset, and source-grounded evaluation questions are complete and locally verified. Repository registration on the course form and pushing the Week 1 tag require external confirmation/approval.

**Week 2:** Work has started in the local working tree on Gemini generation and document ingestion/retrieval experiments. These changes are still in progress and are not part of the Week 1 commit; no Week 2 API behavior or deployment is claimed here.
