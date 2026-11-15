# Combustion Safety Console (frontend)

Static HTML/JS. All data comes from the Space Fire backend API; nothing is hardcoded.

1. Start the backend (`python app.py` in `backend/`, CSVs in `backend/data/experiments/`, AI settings in `.env`).
2. Serve this folder (`python serve_frontend.py --port 8000`) and open http://localhost:8000/overview.html
   (opening the HTML files directly also works; the backend allows any origin by default).

API address: `js/config.js` (`apiBase`, default `http://localhost:5000`), or add `?api=http://host:port` to a page URL.

| Page | Backend endpoints |
|---|---|
| Overview | `/api/statistics`, `/api/investigations`, `/api/investigations/<id>?include_records=true` |
| Investigations | `GET /api/investigations` (search + filters + sort), `GET /api/investigations/<id>`, `POST /api/investigations` (add CSV), `DELETE /api/investigations/<id>`, `/api/summarize` |
| Compare | `/api/compare` (optional AI explanation) |
| Risk Analysis | `/api/rankings`, `/api/rankings/categories`, `/api/investigations` (scenario match), `/api/insights` |
| AI Assistant | `/api/ask` |
| Header status | `/api/health` |

Preprocess investigation packages before starting the backend:

```sh
python backend/preprocess.py
```

Put each of the five investigations in `data/<investigation-id>/` with
`metadata.txt` (ISA tab-separated metadata), `report.pdf`, and `experiments/*.csv`.
PSI-25, PSI-69 and PSI-99 are currently supplied. Preprocessing requires the `pdftotext` command
(Poppler) and writes a CSV, metadata JSON, and chunks JSON per investigation to
`backend/data/experiments/`. Rerun it after changing source files. Multiple tables
within an investigation must share a schema; differing schemas require mapping.

The existing frontend reads profiles through the API. `/api/ask` uses lexical
keyword retrieval over saved source chunks and CSV rows, with page/row provenance
and stable chunk IDs. This is local retrieval, without an embedding database.
PDF text extraction does not interpret figures or perform OCR. AI answers require
the provider settings in `backend/.env.example`; preprocessing needs no AI key.

Findings are verbatim conclusion excerpts extracted from numbered report sections,
with PDF page numbers. They are excerpts rather than an exhaustive report summary.
Saved conclusion passages are also searchable by the assistant. Questions,
summaries, and insights share report/metadata retrieval; report-only vocabulary
can match independently of CSV columns. Ranking weights rare query terms,
normalizes passage length, suppresses contents pages, and favors conclusion
sections for findings questions. Overlapping passages are removed. The context
budget is shared across retrieved investigations, and references describe only
included evidence. Citation validation checks tag membership, not whether every
claim is scientifically supported; verify generated answers against the excerpts.

Run backend regression checks with `.venv/bin/python -m pytest backend/tests -q`
and chart interaction checks with `node tests/chart-hover.cjs`.

The investigation detail page has a bounded, horizontally and vertically scrollable
experiment table and a right-side assistant (stacked below details on small screens).
All detail fields are shown together. The assistant retains separate in-memory
conversations per investigation and sends bounded follow-up history to
`POST /api/investigations/<id>/chat`.

Chart requests use Chart.js 4.5.1, loaded from jsDelivr, with a local SVG preview
when that library cannot load. The AI returns a declarative chart selection;
the backend validates chart types and existing columns and constructs points
from CSV rows. It never executes AI-generated JavaScript or accepts AI-generated
point values. Supported charts are scatter, line, and bar, with exact row tooltips
and CSV download. Missing pairs are skipped and reported. Charts display up to
2,000 points and report any omitted points. Raw values retain source header units.
Run `node tests/investigation-chat.cjs` to check panel state and request handling.


PSI-69 (FLEX) includes 274 experiment records, two reports and two presentations.
Preprocessing accepts PDFs in `reports/` and `presentations/` as well as a root
`report.pdf`. Each PDF retains its own filename, document type, and physical PDF
page numbers in retrieval citations. Conclusions can continue across pages;
presentation summaries are identified as presentation evidence. Appended
`ADDED INFO FROM TEST PLAN:` prose in metadata is preserved in a separate field
and displayed as planned scope. Source document inventories are shown in details.
CSV input accepts UTF-8 or Windows-1252; output is UTF-8. FLEX's specific
`O initial ambient composition; mole fraction` header maps to oxygen. Raw values
stay as fractions in tables and AI-created charts; the existing overview/detail
oxygen charts and filters use normalized percentages. Other source headers and
units, including `Burning rate; mm`, are retained as supplied.


PSI-99 (SAFFIRE-II) includes nine sample rows, two auxiliary records, and four
CSV footnotes. `data/PSI-99/sources.json` records source roles, reviewed source
discrepancies, a transcription of the embedded DOCX sample table, and which CSV
rows provide selected observations. Context documents are searchable but are
not presented as final measured-results reports. DOCX references identify
paragraphs or embedded tables instead of inventing PDF page numbers. The original
CSV is retained unchanged; preprocessing separates notes and auxiliary records.
Approximate/range values and nonnumeric outcomes are not converted to point
estimates or zero. Chart requests support exact numeric cells with unit suffixes
(e.g. `145 s`) and reject columns mixing units without explicit conversion.

Investigation chart controls list only input/outcome pairs with at least two exact,
comparable records and a varying experimental input. Constant inputs, identifiers,
approximations and columns with mixed units cannot create empty plot choices.
Categorical factors such as material are plotted as labelled groups of individual
observations, without averaging or filling missing material names. Default plots
use initial oxygen/final CO for PSI-25, initial droplet diameter/burning rate for
PSI-69, and material/burn time for PSI-99. No chart uses source-row indices as an
experimental axis. Run `node tests/investigation-plots.cjs` for eligibility checks.


The OpenAI connection is configured in `backend/.env`, which is excluded from
version control. Start the backend with `.venv/bin/python backend/app.py` and the
frontend with `.venv/bin/python serve_frontend.py`. The frontend server serves
only public assets: backend files, credentials, raw data, dotfiles and directories
are blocked. Do not serve the repository using an unrestricted static server.
Restart the backend after changing provider settings.

Both chat interfaces use the same grounded research service. `/api/ask` accepts
`question` and optional bounded `history`; investigation chat stays scoped to the
selected investigation. The AI page supports summaries, comparisons, recommended
investigations, transparent relevance rankings, and qualitative future scenarios.
Scores are application heuristics, not NASA assessments, physical hazard levels,
or validated predictions. Recommendations and future implications must be
identified as interpretations with assumptions, cited support, and data gaps.
No model is retrained or fine-tuned; new investigation artifacts become available
through retrieval.

For semantic retrieval, run `.venv/bin/python backend/build_index.py` after
preprocessing. This sends text chunks to the configured OpenAI embedding API
and stores vectors in local SQLite; source text/provenance remains in the saved
artifacts. The default embedding model is `text-embedding-3-small`. Keyword search
and semantic similarity are combined when the index is current and the provider
is reachable. A missing/stale index or embedding outage keeps keyword retrieval
active. Rebuild after changing source artifacts. `/api/health` reports the model
configuration and whether the semantic index is current; configured does not
prove credentials, billing, or network connectivity are valid.

Response defaults are brief (80–140 words; up to 200 for comparisons/rankings),
with detail on request. Current local settings use a 16,000-character evidence
budget, six records and three source passages per investigation, compact recent
chat history, and low OpenAI reasoning effort. Source profiles and chunks are
cached by file modification time and size, so edits and uploads invalidate them.
Semantic vectors and successful repeated query embeddings are cached; embedding
outages back off briefly and fall back to keyword retrieval. API response
`timing_ms` separates generation time from retrieval time on the main assistant.
Restart the backend to apply changes to `.env`. Local retrieval benchmarks do
not measure network/provider latency; test end-to-end latency on the deployment.

A presentation-oriented overview and suggested slide sequence are in
[summary.md](summary.md).
