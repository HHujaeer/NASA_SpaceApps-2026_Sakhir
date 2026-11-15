# NASA Space Fire Intelligence Dashboard – Backend

Flask REST API that reads standardized NASA experiment CSVs **on demand** and adds grounded AI features
(research assistant, summaries, comparison explanations, fire safety insights) plus transparent,
application-generated relevance ranking. No database and no auth; uploaded CSVs are stored as plain files in the data directory.

```
backend/
  app.py  config.py  requirements.txt  .env.example
  services/  csv_service.py  ai_service.py  ranking_service.py  comparison_service.py  research_service.py
  data/experiments/   <- put the NASA *.csv files here
  tests/
```

## Run

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Python 3.11+
pip install -r requirements.txt
cp .env.example .env                                   # then edit (see below)
python app.py                                          # http://localhost:5000/api/health
python -m pytest                                       # run the tests
```

Drop CSVs into `backend/data/experiments/` (or set `DATA_DIR`), or upload them with `POST /api/investigations`. Each file = one investigation; the file name
(without `.csv`) is its id; each row is one record. No restart is needed when files change.

### AI configuration (model intentionally not defaulted)
Set in `.env`: `AI_PROVIDER` (`openai` | `xai` | `custom`), `AI_MODEL`, and the key
(`OPENAI_API_KEY`, `XAI_API_KEY`, or generic `AI_API_KEY`). `custom` + `AI_BASE_URL` works with any
OpenAI-compatible endpoint. To add another compatible provider, add an entry to `PROVIDERS` in `config.py`.
Keys never leave the backend. Without AI config, all data/ranking/comparison endpoints still work; AI endpoints
return a clear `503 ai_not_configured` (with the retrieved references attached).

## Column detection
Columns are matched by name (aliases in `config.FIELD_ALIASES`): experiment name, material/fuel, oxygen, pressure,
flow, gravity, sensors, objective, mission, source/reference, findings, notes. Other numeric columns become
*measurements*. Put units in headers (`Pressure_kPa`, `O2_pct`, `Pressure (psi)`) so values can be normalized
(kPa, %, g) for filtering/comparison; raw values are always returned unchanged. With no recognizable unit a
value is returned as-is but **not** converted or compared numerically across files. Missing cells
(`""`, `NA`, `N/A`, `null`, `-`, …) are returned as `null`, never filled in.

## Response format
```json
{"success": true,  "data": {...}, "meta": {...}}
{"success": false, "error": {"code": "invalid_request", "message": "...", "details": {...}}}
```
Statuses: 400 invalid input · 404 unknown investigation/endpoint · 409 id already exists · 413 upload too large · 422 unreadable CSV · 429/502/503/504 AI problems.

## Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | status, CSV count, AI config status |
| GET | `/api/investigations` | list/search/filter/sort: `q, fuel, sensor, min_oxygen, max_oxygen, min_pressure_kpa, max_pressure_kpa, min_gravity_g, max_gravity_g, sort(id\|name\|row_count\|completeness), order, limit, offset` |
| POST | `/api/investigations` | upload a CSV: multipart `file`, optional `id` (default: file name) and `overwrite=true`. 201 created / 200 replaced / 409 id exists / 422 unreadable CSV; limit `MAX_UPLOAD_BYTES` (5 MB) |
| DELETE | `/api/investigations/<id>` | delete that investigation's CSV file |
| GET | `/api/investigations/<id>` | one investigation; `?include_records=true&limit=&offset=` adds raw rows |
| GET | `/api/statistics` | aggregate stats across all files |
| GET | `/api/rankings/categories` | ranking categories |
| GET / POST | `/api/rankings` | rank by category (`?category=`); POST accepts `{category, weights, limit}` |
| POST | `/api/compare` | `{ids:[...], explain:false}` |
| POST | `/api/ask` | `{question}` |
| POST | `/api/summarize` | `{investigation_id}` |
| GET | `/api/insights/topics` · POST `/api/insights` | `{topic, investigation_ids?}` |

Ranking categories: `iss_spacecraft, lunar_habitat, mars_habitat, pressurized_rover, fire_prevention, fire_detection,
fire_suppression, predictive_modeling`. Insight topics: `material_flammability, oxygen_concentration,
microgravity_combustion, smoke_detection, fire_suppression, future_habitats`.

## Examples
*(Outputs below were produced by running this code on tiny **synthetic** test CSVs, not NASA data. Long fields trimmed.)*

```bash
curl "localhost:5000/api/investigations?q=smoke&limit=1"
# meta: {"total": 1, "limit": 1, "offset": 0, "unreadable_files": []}

curl localhost:5000/api/investigations/nope
# 404 {"success": false, "error": {"code": "investigation_not_found", "message": "No investigation with id 'nope'."}}

curl -X POST localhost:5000/api/compare -H 'Content-Type: application/json' \
     -d '{"ids":["flame_spread","smoke_detection"]}'
```
```json
{"success": true, "data": {
  "similarities": ["oxygen concentration: ranges overlap between 21 and 26.5 (E1: 21–30; E2: 21–26.5; normalised to %)."],
  "differences":  ["sensors: differs (E1: thermocouple, camera; E2: photoelectric, ionization)."],
  "not_available": ["airflow is not reported in SmokeStudy (E2)."],
  "...": "investigations, parameters, results, optional explanation"}}
```

```bash
curl "localhost:5000/api/rankings?category=lunar_habitat&limit=1"
```
```json
{"success": true, "data": {
  "category": "lunar_habitat", "disclaimer": "These are application-generated relevance scores ... not NASA-approved rankings ...",
  "weights_percent": {"mission_relevance": 30.0, "fire_safety_relevance": 25.0, "data_quality": 20.0,
                      "environmental_similarity": 15.0, "predictive_modeling_value": 10.0},
  "ranked": [{"rank": 1, "id": "flame_spread", "name": "TestFlame", "score": 45.2,
    "criteria": {"mission_relevance": {"score": 0.0, "weight_percent": 30.0, "weighted_points": 0.0, "explanation": "No mission keywords ... scored 0 ..."},
                 "data_quality": {"score": 79.7, "weighted_points": 15.93, "explanation": "Completeness 92% ..."}, "...": "..."},
    "supporting_data": {"file": "flame_spread.csv", "row_count": 4, "completeness": 0.925}}]}}
```

```bash
curl -X POST localhost:5000/api/ask -H 'Content-Type: application/json' \
     -d '{"question":"How did the smoke detector alarm behave?"}'
```
```json
{"success": true, "data": {
  "answerable": true,
  "answer": "## Experimental results (from the data)\n... [E1:R1].\n## AI interpretation\n... [E1].\n## Data gaps\n...",
  "sections": {"experimental_results": "...", "ai_interpretation": "...", "data_gaps": "..."},
  "retrieval": [{"tag": "E1", "investigation_id": "smoke_detection", "row_selection": "matched", "records_used": [1, 2, 3]}],
  "references": [{"tag": "E1:R1", "type": "record", "file": "smoke_detection.csv", "row_number": 1, "source_reference": "REF-S1"}],
  "citation_check": {"cited": ["E1", "E1:R1"], "unknown_citations": [], "all_citations_valid": true},
  "ai": {"provider": "custom", "model": "demo-model"}}}
```
(That AI text came from a local stand-in server used to exercise the real HTTP path; it is not a real model answer.)
A question with no matching records returns `{"answerable": false, "answer": null, "message": "No records in the NASA CSV files matched this question."}` and **does not call the AI**.

## How the "no outside facts" rules are enforced
- Only rows retrieved from the CSVs (plus backend-computed min/max/mean over those files) are sent to the model, inside `<data_context>`; the system prompt forbids outside facts, requires `[E1:R5]`-style citations, separates *Experimental results* / *AI interpretation* / *Data gaps*, and tells the model to ignore instructions found inside the data.
- References are built by the backend from the retrieved rows, never by the model. `citation_check` flags citations the model invented.
- No relevant data → no AI call. AI failure → error with the retrieved references still attached (no made-up fallback answer).
- Prompts constrain the model but cannot guarantee compliance; `citation_check` and the always-present references let the UI show users what the answer rests on.

## Ranking notes
Scores are application-generated (30/25/20/15/10 weights, editable via `RANKING_WEIGHTS` or per-request `weights`) and every criterion
carries a plain-language explanation. They rely on keywords/columns found in the CSVs, so a file lacking mission metadata scores 0 on
mission relevance (stated in the explanation). The reference habitat atmospheres in `config.ENV_PROFILES` are **placeholder assumptions** —
please replace them with the values your program uses.

## Adjusting for the frontend
Routes live in `app.py` only; response shaping is in the services. Renaming routes or fields is a local change.
