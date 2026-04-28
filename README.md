# Clinical Bottleneck Radar

An operational command center for hospital throughput. Reads patient notes,
identifies what is blocking each patient's care progression, and recommends
the next operational action with an owner and urgency.

Built for the Palantir AIP build challenge.

## What it does

For every patient in the queue, the Radar answers four questions:

1. **What is blocking this patient?** (awaiting consult, awaiting imaging,
   discharge placement, missing standard-of-care step, medication risk,
   readmission risk)
2. **Why are they stuck?** (extracted evidence quoted from the note)
3. **What should happen next?** (concrete recommended action)
4. **Who owns it?** (charge nurse / physician / pharmacist / case manager / social worker)

Silent-failure detection is built in: the system cross-references each patient
against a library of standard-of-care protocols (sepsis bundle, ACS, stroke,
CHF, pneumonia, AKI, DKA) and flags when an expected action is missing.

## Architecture

```
backend/   FastAPI + SQLite + clinical NLP pipeline
frontend/  React + TypeScript + Vite, Palantir-style dark UI
```

### Backend stack

- **FastAPI** REST API
- **SQLite** for the demo (the ontology layer in a real Foundry deployment)
- **scikit-learn / sentence-transformers** for ICD-10 retrieval
- **Custom rule engine** for protocol matching and silent-failure detection
- **spaCy-style** entity extraction (vitals, labs, meds, dispo signals)

### Frontend stack

- **React 18 + TypeScript + Vite**
- Dense tabular UI, monospace numerals, signal-color status
- No chart-junk, no decorative animation

## Running locally

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.ingest          # build DB from notional notes
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

## Data

All patient data is **notional** and generated for this demonstration.
No real patient information is used.
