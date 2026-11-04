# SafeShift Week 2 Verification Report

**Report date:** 2026-11-04  
**Repository:** `Haresh-web-code/SafeShift`  
**Scope:** Security review, Week 2 verification, and release preparation. No commit, tag, push, or deployment was performed.

## Executive summary

Week 2 API features are implemented and covered by offline tests with mocked Gemini responses. Local Ruff, pytest, dependency, and diff checks pass. The Docker image built successfully, and the API container ran healthy as a non-root user with the sample OSHA retrieval index available. Container `/health` and `/usage` requests and an in-container retrieval probe succeeded.

The latest hosted GitHub Actions runs succeeded for repository commit `c28e9a2` (the current Git `HEAD`). This checkout has uncommitted changes, so those local changes are **not** covered by the hosted run. The optional database profile parses, but the database was not started because its local password secret file is absent. No deployment or release was performed.

## Security review

| # | Severity | File | Lines | Vulnerability | Confidence |
|---|----------|------|-------|---------------|------------|
| 1 | 🟡 MEDIUM | [.dockerignore](./.dockerignore) | 8 | `.secrets/` was not excluded from the Docker build context, which could send a local database password to a remote builder. Fixed by adding `.secrets/` to `.dockerignore`. | 8/10 |

Additional checks:

- `.env` is ignored by Git and is not tracked. No `.secrets/` paths are tracked.
- A pattern-based scan of tracked text files found no likely API keys, passwords, private keys, or access tokens. The scan emitted no matched values.
- `.env.example` contains placeholders, not actual credentials. Its Gemini names correspond to the application configuration. The optional PostgreSQL user/database names are non-secret defaults; its password is supplied as a Compose secret file.
- `.dockerignore` excludes environment files, `.git/`, caches, raw data, generated chunks, and `.secrets/`. The Dockerfile copies only the application, `tools/search.py`, the ingest script, and sample PDFs.
- The API container runs as UID 1000. `/app/.env` is not present in the container; Compose supplies the local `.env` through `env_file`.
- The API logs inspected during the runtime check contained normal startup and health-request messages and no credential-like markers.
- The database profile uses a file-backed Docker secret for `POSTGRES_PASSWORD_FILE`; its configuration parses, but the required local file `.secrets/postgres_password` is currently absent, so the database was not started.

**Credential rotation:** A prior Compose output/report may have exposed a resolved credential. Treat any Gemini API key or database credential shown there as compromised. If not already done, revoke/rotate the affected credential(s) and review the provider access logs. No credential value is reproduced here.

## Changes made or present in the Week 2 worktree

| File | Purpose and change |
|---|---|
| [.dockerignore](./.dockerignore) | Excludes `.secrets/` and unnecessary local data from the Docker build context. |
| [.env.example](./.env.example) | Provides placeholder-only Gemini configuration; optional fallback model is blank. |
| [.gitignore](./.gitignore) | Ignores `.env`, `.secrets/`, generated chunks, and local development files. |
| [Dockerfile](./Dockerfile) | Builds the local OSHA index from sample PDFs, copies only runtime retrieval code, runs as a non-root user, and defines a health check and production startup command. |
| [compose.yaml](./compose.yaml) | Configures the API with `.env` as an environment file and an optional pgvector service with a file-backed password secret. |
| [requirements.txt](./requirements.txt) | Corrects the malformed final dependency entry that previously prevented Docker's pip install step. |
| [README.md](./README.md) | Documents setup, API behavior, deployment preparation, limitations, and verified status. |
| [PROGRESS.md](./PROGRESS.md) | Records evidence-based Week 2 status and remaining manual tasks. |
| [app/config.py](./app/config.py) | Defines typed Gemini settings, aliases, timeout/deadline/retry limits, and optional cost rates. |
| [app/llm.py](./app/llm.py) | Implements configurable Gemini generation, bounded transient retries, model fallback, deadlines, and no retry after partial stream output. |
| [app/main.py](./app/main.py) | Implements chat, SSE streaming, health and usage endpoints; returns safe fallbacks, citations, timings, status and usage data. |
| [app/schemas.py](./app/schemas.py) | Defines structured request, response, citation, and usage models. |
| [app/usage.py](./app/usage.py) | Tracks process-local requests, statuses, retries, token totals, and cost estimates. |
| [ingest.py](./ingest.py) | Extracts page-numbered text chunks from PDFs for local retrieval. |
| [manifest.json](./manifest.json) and [data/manifest.csv](./data/manifest.csv) | Record document metadata and the downloader manifest format. |
| [tools/answer.py](./tools/answer.py) | Provides the standalone answer utility with the requested Ruff cleanup. |
| [tools/download.py](./tools/download.py) | Provides the OSHA download helper with corrected imports and local variable handling. |
| [tools/search.py](./tools/search.py) | Implements local lexical search over the generated chunk index. |
| [tools/test_gemini.py](./tools/test_gemini.py) | Provides a manual Gemini smoke-test utility; not used by automated tests. |
| [tools/urls.txt](./tools/urls.txt) | Lists source URLs for the downloader. |
| [tests/conftest.py](./tests/conftest.py) | Creates isolated API test settings that do not load local credentials. |
| [tests/test_chat.py](./tests/test_chat.py) | Tests structured API responses, citations, empty retrieval, safe fallback, SSE events and usage with mocks. |
| [tests/test_llm.py](./tests/test_llm.py) | Tests Gemini success, 503s, timeouts, retry limits, fallback models, permanent errors and stream failures using fakes. |
| [WEEK2-VERIFICATION-REPORT.md](./WEEK2-VERIFICATION-REPORT.md) | Records this verification and remaining release requirements. |

## Verification results

| Check | Result |
|---|---|
| `ruff check .` | **Passed** — “All checks passed!” |
| `python -m pytest -q` | **Passed** — 27 tests passed in 0.18 seconds. Tests use mocked/fake Gemini responses and do not require a live API key. |
| `python -m pip check` | **Passed** — no broken requirements found. |
| `git diff --check` | **Passed** — no whitespace errors. |
| `git check-ignore .env` | **Passed** — `.env` is ignored. |
| `docker compose config --quiet` | **Passed**. |
| `docker compose --profile database config --quiet` | **Passed**; this validates configuration only, not database startup. |
| `docker compose build` | **Passed** — image built; ingestion generated 207 chunks from the two sample PDFs. |
| `docker compose up -d` / `docker compose ps` | **Passed** — API container started and reported healthy. |
| `GET /health` in container | **Passed** — returned `status: ok`, app `SafeShift`, environment `local`. |
| `GET /usage` in container | **Passed** — returned structured zero-count usage before any chat request. |
| Container identity and local retrieval | **Passed** — UID 1000; `chunks.jsonl` exists; retrieval returned OSHA document/page citations (pages 7 and 15). The container had no mounted `/app/.env`. |
| API chat, stream, retry and fallback behavior | **Passed locally in mocked tests**. No live Gemini request was made from the Docker runtime check. |
| Optional PostgreSQL/pgvector runtime | **Not verified** — `.secrets/postgres_password` is absent. PostgreSQL/pgvector is not connected to retrieval. |
| Hosted GitHub Actions | **Passed for commit `c28e9a2`** on 2026-11-03; the currently uncommitted worktree changes are not covered. |
| Deployment | **Not performed** — no cloud resources or live URL were created. |

The CI workflow runs on pushes and pull requests, uses Python 3.12, installs `requirements-dev.txt`, runs full-project `ruff check .`, and runs `python -m pytest -q`. Check the repository's **Actions** tab after the pending changes are committed and pushed to verify those changes in a hosted run.

## Week 2 milestone status

| Requirement | Status | Evidence / limitation |
|---|---|---|
| `GET /health`, `POST /chat`, `POST /chat/stream`, and `GET /usage` | **COMPLETE** | API tests pass; health and usage were also called in the container. |
| Structured responses and OSHA document/page citations | **COMPLETE** | Verified in mocked API tests and in-container retrieval. |
| Empty-retrieval, retrieval-error and Gemini-unavailable safe behavior | **COMPLETE** | Mocked API tests; no unsupported safety procedure is generated by fallback paths. |
| Bounded Gemini timeout, transient retry, fallback model and no replay after partial stream | **COMPLETE** | Exercised with mocked/fake Gemini client tests. |
| Usage and optional estimated cost tracking | **COMPLETE** for process-local tracking | `/usage` schema, token/retry/model totals and configured cost estimate are tested. Counters reset on process restart and are not persisted. |
| Ruff, pytest and dependency checks | **COMPLETE locally** | Ruff, all 27 tests, and `pip check` passed. |
| Docker image and API runtime | **COMPLETE locally** | Image built; container healthy; health/usage and retrieval verified. |
| Optional PostgreSQL/pgvector service | **PARTIALLY COMPLETE** | Profile configuration parses. Runtime was not started because the local secret file is absent; database is not used by retrieval. |
| GitHub Actions | **PARTIALLY COMPLETE** | Workflow is configured and a hosted run passed for the existing HEAD; current uncommitted changes need a new hosted run. |
| Deployment and live URL | **NOT COMPLETE** | No deployment was performed. |
| Week 2 tag and push | **NOT COMPLETE** | No commit, tag, or push was created. |

## Week 3 readiness

SafeShift is ready to begin Week 3 implementation planning, but Week 3 features are not complete. The current retrieval uses two sample OSHA PDFs (116 pages), local PDF text extraction, chunking, and lexical search. The following remain future work:

- Ingest and validate 500+ OSHA pages with improved PDF parsing and page/heading preservation.
- Generate embeddings and store/query them in PostgreSQL/pgvector.
- Add `POST /ask` with source citations.
- Evaluate and record scored results for 10 safety questions.

## Manual actions and release preparation

1. Rotate any Gemini API key or database credential exposed by the prior Compose output/report, if that has not already been done. Replace it in local secret configuration and inspect provider access logs.
2. To run the optional database profile, create `.secrets/postgres_password` locally with a strong password. Do not commit the file. The database is not currently used by retrieval.
3. Review the uncommitted worktree and staged-file list before release. `.env` and `.secrets/` must remain unstaged. No files are staged by this verification, and no commit/tag/push was run.
4. To prepare the release after review, run these commands yourself; they have **not** been run:

   ```powershell
   git add .
   git status
   git diff --cached --check
   git commit -m "Complete Week 2 SafeShift implementation"
   git tag week-2
   git push origin main
   git push origin week-2
   ```

5. After pushing, check GitHub **Actions** for a successful run on the new commit. Approve deployment and any associated costs separately; no deployment has occurred.
