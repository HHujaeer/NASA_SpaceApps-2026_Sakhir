# Combustion Safety Console (frontend)

Static HTML/JS. All data comes from the Space Fire backend API; nothing is hardcoded.

1. Start the backend (`python app.py` in `backend/`, CSVs in `backend/data/experiments/`, AI settings in `.env`).
2. Serve this folder (`python -m http.server 8000`) and open http://localhost:8000/overview.html
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
