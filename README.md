# <SafeShift>

## Problem
<Supervisors need safety procedures (lockout, machine guarding, chemical handling) during a shift, from thick safety manuals. A slow tool is useless on the shop floor, and nobody knows which part of the system makes it slow.>

## Who it is for
<Safety officer at a Sriperumbudur contract manufacturing company running several client production lines>

## Signature feature
<Latency receipt under each answer showing time spent in each stage.>

## Hardest problem (my interview story)
<Observability and latency budget. Every request is traced with OpenTelemetry spans for embedding, search, re-rank and generation, and dashboards show p50/p95 per stage. The student sets a 4-second p95 budget and shows which changes brought each stage under its share.>

## Dataset
| Source | Link | Documents | Pages | Licence / terms |
|---|---|---|---|---|
| <name> | <url> | <n> | <n> | <licence> |

## 10 real questions
See [docs/QUESTIONS.md](docs/QUESTIONS.md).

## Run it
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                 # Windows: copy .env.example .env
uvicorn app.main:app --reload
curl localhost:8000/health
```

## Live link
<Added in Week 2>
