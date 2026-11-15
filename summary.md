# Combustion Safety Console — Technical Project Summary

## Purpose and challenge alignment

The project is an interactive, AI-powered web dashboard that turns complex combustion research files into searchable evidence, comparable measurements, and concise fire-safety insights. It addresses the challenge of making NASA's experimental results easier to find, compare, summarize, rank, and interpret for human space exploration.

The implementation uses **three investigations as a representative sample**. The focus is a reusable software pipeline and interface that can expand as additional research becomes available.

The application supports research into prevention, detection, and suppression for habitable crew environments. It helps users assess which available evidence is relevant to spacecraft, space stations, lunar or Martian habitats, and pressurized rovers. Its interpretations support research and engineering judgment; they do not certify safety or replace validated predictive models.

## Software architecture

The code separates document processing, data access, retrieval, AI generation, and presentation:

```text
Source CSV, metadata, PDF, and DOCX files
                    ↓
           Python preprocessing
                    ↓
 Structured records + investigation profiles
       + source-linked evidence chunks
                    ↓
               Flask API
          ↙         ↓         ↘
 Comparison     Shared RAG     Relevance
  service        service       ranking
                    ↓
         OpenAI-generated response
          + citations / chart plan
                    ↓
       HTML / CSS / JavaScript dashboard
```

The frontend requests structured data through REST endpoints. API credentials and model calls stay on the backend. Both the investigation chat and the main AI page use the same research service, keeping their grounding and citation behavior consistent.

## Data preprocessing

**Main file:** `backend/preprocess.py`

Preprocessing converts heterogeneous source files into artifacts the application can reuse without extracting documents on every request:

- Reads experiment tables and tab-separated metadata, including quoted multiline values.
- Extracts PDF text with Poppler's `pdftotext` and DOCX paragraphs through XML parsing.
- Separates experimental sample rows from footnotes and auxiliary records when configured.
- Identifies report conclusion and presentation-summary passages, including conclusions that continue across pages.
- Produces CSV records, a JSON investigation profile, and a JSON evidence-chunk collection.
- Assigns stable chunk identifiers and preserves source locations: PDF pages, CSV rows, DOCX paragraphs, and reviewed embedded-table references.

Optional source manifests capture document roles, reviewed transcriptions, and known inconsistencies. Context documents and test plans remain distinguishable from measured findings. Raw source files remain unchanged.

## Data access and API design

**Main files:** `backend/app.py`, `backend/services/csv_service.py`

The Flask API exposes investigation browsing, filtering, statistics, comparisons, rankings, summaries, and chat. Responses use a consistent success/error envelope, allowing the frontend to handle configuration, validation, and provider failures predictably.

The data service builds profiles containing detected fields, conditions, measurement statistics, missing-data information, source references, and document inventories. Unit normalization supports compatible filters and displays while raw table values retain their original representation.

Representative endpoints include:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/investigations` | Search, filter, and sort investigations |
| `GET /api/investigations/<id>` | Retrieve metadata, conditions, findings, and optional records |
| `POST /api/ask` | Ask questions across the evidence collection |
| `POST /api/investigations/<id>/chat` | Ask questions or request charts within one investigation |
| `POST /api/compare` | Generate structured comparisons |
| `GET /api/rankings` | Retrieve configurable relevance scores |
| `GET /api/health` | Inspect backend, model configuration, and semantic-index status |

## Retrieval-augmented AI

**Main files:** `backend/services/research_service.py`, `backend/services/semantic_service.py`, `backend/services/ai_service.py`

The system uses **retrieval-augmented generation (RAG), not model training or fine-tuning**. The model receives selected evidence at question time.

The retrieval flow is:

1. Validate the question and compact recent conversation history.
2. Identify explicitly named investigations and the requested task.
3. Retrieve relevant source passages and experiment records.
4. Combine keyword matching with semantic similarity when a current embedding index is available.
5. Remove overlapping passages and build an evidence context within a character budget.
6. Request a concise answer grounded in that context.
7. Return source references, citation checks, and truncation information with the answer.

The optional semantic index uses OpenAI embeddings stored in local SQLite. Index fingerprints detect source changes; missing, stale, or temporarily unavailable semantic retrieval falls back to keyword search.

Historical chat helps resolve follow-up questions but is not treated as scientific evidence. Prompts distinguish measured observations, simulation results, planned objectives, interpretations, and data gaps. Citation checks validate reference tags; they do not independently establish the truth of every generated statement.

## Summaries, rankings, and interpretation

**Main files:** `backend/services/decision_service.py`, `backend/services/ranking_service.py`, `backend/services/comparison_service.py`

The main assistant supports concise summaries, cross-investigation comparisons, question-specific recommendations, and qualitative future scenarios.

Ranking is implemented with transparent application rules. Category scoring considers mission relevance, fire-safety relevance, data quality, environmental similarity, and modeling value. Question-specific ordering currently blends **65% category relevance with 35% query-term coverage**. The interface exposes the methodology alongside the ordering.

Comparison code examines shared and differing conditions, materials, measurements, and missing information. The AI explains relevant evidence and limitations rather than assuming experiments are directly interchangeable.

For future scenarios, the system describes supported qualitative implications, assumptions, and validation needs. It does not generate validated numerical forecasts, physical hazard probabilities, or NASA-approved safety priorities. Configurable habitat reference conditions are application assumptions, not new experimental measurements.

## Interactive frontend and visualization

**Main directories:** `js/models/`, `js/views/`, `js/controllers/`, `css/`

The frontend uses a lightweight model–view–controller structure:

- **Models** fetch API data, adapt records, maintain conversation state, and determine valid graph combinations.
- **Views** render investigation details, tables, charts, comparison screens, and AI responses.
- **Controllers** connect user actions to loading, filtering, graph selection, and chat requests.

Investigation pages show all detail fields together, a bounded scrollable table with sticky headers, source-linked findings, and a right-side chat panel. The layout adapts to smaller screens. Text uses the available width, and lead paragraphs preserve source newlines.

Graph selectors are generated from actual paired data. They exclude unusable combinations, constant inputs, identifiers, and incompatible units. The x-axis represents an experimental input or a labelled category rather than an arbitrary row index. Hover interaction uses a vertical dotted guide, highlights an observed point, and displays its exact values.

AI-requested charts use Chart.js, with an SVG preview if the library is unavailable. The model returns a declarative chart type and column selection. Backend validation constructs the points from source records; it never executes AI-generated JavaScript or accepts invented point values. Chart data can be downloaded as CSV.

## Performance and configuration security

Repeated document extraction is avoided through preprocessing. Parsed profiles and source chunks are cached until source-file signatures change. Semantic vectors and successful repeated query embeddings are reused, while temporary embedding failures trigger a brief backoff.

Prompt context, retrieved records, source passages, and conversation history are bounded. Default AI responses target 80–140 words, with modestly longer comparisons and rankings. The configured OpenAI reasoning effort is reduced, and API timing fields help distinguish retrieval work from generation time.

API keys remain in backend configuration excluded from version control. `serve_frontend.py` restricts static serving to public assets and blocks backend files, raw data, dotfiles, and directory listings.

## Validation and current limits

The current verification includes **81 passing backend tests**, plus JavaScript checks for graph eligibility, hover behavior, chat state, comparison-table rendering, citations, and ranking cards. Tests cover source provenance, missing values, conflicting source information, cache invalidation, semantic fallback, and private-file access restrictions.

The representative sample demonstrates the software pipeline rather than comprehensive coverage of combustion science. Live model latency and answer quality require deployment testing with working API connectivity. Broader evaluation should include expert-reviewed questions, retrieval relevance, citation faithfulness, and evidence completeness.

## Suggested presentation structure

1. **Challenge:** Make complex combustion evidence easier to find, compare, and interpret.
2. **Architecture:** Show the path from source files to preprocessing, API, RAG, and dashboard.
3. **Data engineering:** Explain reusable profiles, provenance, missing values, and document roles.
4. **Interface demo:** Browse details, scroll records, and select a valid input/outcome graph.
5. **AI demo:** Ask for a short cited answer, then a follow-up question.
6. **Decision support:** Show a comparison and an explainable relevance ranking.
7. **Engineering quality:** Discuss validation, caching, safe chart generation, and credential separation.
8. **Next steps:** Expand the representative sample, evaluate with expert-reviewed answers, and measure live end-to-end performance.

**Closing message:** The contribution is a reusable, traceable software system that turns research files into interactive evidence and grounded decision support for space-exploration fire safety.
