# Progress

Commit after each class. Create a weekly tag after the corresponding work is complete. Do not push commits or tags without approval.

## Week 1 — SafeShift foundation

- [x] Repository initialized from the Examate starter (repository history and starter README verified)
- [ ] Register the repository on the project form (requires owner confirmation; cannot be verified from this repository)
- [x] Complete the README with project scope, dataset, setup, runtime, limitations, and progress
- [x] Verify `GET /health` returns a successful response
- [x] Document 10 realistic evaluation questions with PDF-page references and an out-of-scope question
- [x] Collect and document 116 pages across two OSHA publications; include sample PDFs in `data/sample/`
- [ ] Push the `week-1` tag (local commit/tag creation is part of this delivery; pushing requires approval)

## Week 2 — in progress

Week 2 implementation remains local; do not include it in the Week 1 commit.

- [x] `POST /chat`, `POST /chat/stream`, `GET /health`, and `GET /usage` implemented; offline tests use mocked Gemini
- [x] OSHA citations, empty-retrieval responses, safe Gemini fallback, bounded retries/deadlines, fallback model, and no replay after partial stream output tested locally
- [x] Local `ruff check .` and `python -m pytest -q` pass (27 tests, including a mocked API-level Gemini 503 fallback)
- [x] Docker Compose configuration parses; image builds; API container is healthy, runs as non-root, and `/health`, `/usage`, and in-container sample retrieval were checked on 2026-11-04
- [x] GitHub Actions uses Python 3.12 and full-project Ruff/pytest; a hosted run succeeded for commit `c28e9a2` (current uncommitted changes are not covered by that run)
- [x] Container startup, health check, retrieval sample inclusion, and deployment preparation documented
- [ ] Deploy the application and add a live link to README (not deployed; requires owner approval and credentials/budget)
- [ ] Start the optional PostgreSQL/pgvector profile (configuration parses, but the database password secret file must be created manually; database is not used by retrieval)
- [ ] Create and push the `week-2` tag (push requires owner confirmation)

## Week 3

- [ ] Parser keeps page numbers and headings
- [ ] 500+ pages chunked, embedded, and stored in pgvector
- [ ] `POST /ask` answers with `[document, page]` citations
- [ ] `docs/EVAL_v0.md` contains scored results for the 10 questions
- [ ] Create and push the `week-3` tag

## Daily log

| Date | What I did today | Commit |
|---|---|---|
| | | |
