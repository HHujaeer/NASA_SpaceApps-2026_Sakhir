"""Flask REST API for the NASA Space Fire Intelligence Dashboard.

Response envelope (all endpoints):
  success: {"success": true,  "data": {...}, "meta": {...}}
  failure: {"success": false, "error": {"code": "...", "message": "...", "details": {...}?}}

Run:  python app.py        (or: flask --app app run)
"""
from __future__ import annotations

import os

from flask import Flask, jsonify, request

from config import Config
from services.ai_service import AIService, AIServiceError
from services.comparison_service import ComparisonService
from services.csv_service import (CsvService, DataFileError, InvalidRequest, InvestigationExists,
                                  InvestigationNotFound)
from services.ranking_service import RankingService
from services.research_service import ResearchService


# --------------------------------------------------------------------------- #
# Response helpers
# --------------------------------------------------------------------------- #
def ok(data, **meta):
    return jsonify({"success": True, "data": data, "meta": meta})


def fail(code, message, status, details=None):
    error = {"code": code, "message": message}
    if details:
        error["details"] = details
    return jsonify({"success": False, "error": error}), status


def _body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise InvalidRequest("Request body must be a JSON object.")
    return body


def _num(args, name):
    raw = args.get(name)
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except ValueError:
        raise InvalidRequest(f"Query parameter '{name}' must be a number.") from None


def _int(args, name, default, lo=0, hi=1000):
    raw = args.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError:
        raise InvalidRequest(f"Query parameter '{name}' must be an integer.") from None
    if not lo <= value <= hi:
        raise InvalidRequest(f"Query parameter '{name}' must be between {lo} and {hi}.")
    return value


def _bool(value):
    return str(value).lower() in ("1", "true", "yes")


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #
def create_app(config=None):
    config = config or Config()
    app = Flask(__name__)
    app.json.sort_keys = False
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_BYTES + 64 * 1024  # file plus form fields

    csv_service = CsvService(config)
    ai_service = AIService(config)
    app.extensions["services"] = {
        "csv": csv_service, "ai": ai_service,
        "ranking": RankingService(config, csv_service),
        "comparison": ComparisonService(config, csv_service, ai_service),
        "research": ResearchService(config, csv_service, ai_service),
    }
    svc = app.extensions["services"]

    _setup_cors(app, config)
    _register_errors(app)

    # ------------------------------ system ------------------------------- #
    @app.get("/api/health")
    def health():
        return ok({"status": "ok", "data_directory_exists": csv_service.data_dir_exists(),
                   "csv_files_found": len(csv_service.list_investigation_ids()), "ai": ai_service.status(),
                   "retrieval": svc["research"].semantic.status()})

    # --------------------------- investigations --------------------------- #
    @app.get("/api/investigations")
    def list_investigations():
        a = request.args
        ranges = {}
        for field, lo_name, hi_name in (("oxygen", "min_oxygen", "max_oxygen"),
                                        ("pressure", "min_pressure_kpa", "max_pressure_kpa"),
                                        ("gravity", "min_gravity_g", "max_gravity_g")):
            lo, hi = _num(a, lo_name), _num(a, hi_name)
            if lo is not None or hi is not None:
                ranges[field] = (lo, hi)
        limit, offset = _int(a, "limit", None), _int(a, "offset", 0, hi=10**6)
        items, total, errors = svc["csv"].list_investigations(
            q=a.get("q"), fuel=a.get("fuel"), sensor=a.get("sensor"), ranges=ranges,
            sort=a.get("sort", "id"), order=a.get("order", "asc"), limit=limit, offset=offset)
        return ok(items, total=total, limit=limit, offset=offset, unreadable_files=errors)

    @app.get("/api/investigations/<inv_id>")
    def get_investigation(inv_id):
        include = _bool(request.args.get("include_records", "false"))
        data = svc["csv"].get_investigation(inv_id, include, _int(request.args, "limit", 100, 1, 1000),
                                            _int(request.args, "offset", 0, hi=10**6))
        return ok(data)

    @app.post("/api/investigations")
    def add_investigation():
        """Upload a CSV (multipart field 'file'; optional 'id' and 'overwrite') as a new investigation."""
        upload = request.files.get("file")
        if upload is None:
            raise InvalidRequest("Send the CSV as multipart/form-data in the 'file' field.")
        if upload.filename and not upload.filename.lower().endswith(".csv"):
            raise InvalidRequest("Only .csv files can be uploaded.")
        inv_id = (request.form.get("id") or "").strip() or csv_service.id_from_filename(upload.filename)
        data, replaced = csv_service.add_investigation(
            inv_id, upload.read(), overwrite=_bool(request.form.get("overwrite", "false")))
        return ok(data, replaced=replaced), (200 if replaced else 201)

    @app.delete("/api/investigations/<inv_id>")
    def delete_investigation(inv_id):
        return ok(svc["csv"].delete_investigation(inv_id))

    @app.post("/api/investigations/<inv_id>/chat")
    def investigation_chat(inv_id):
        body = _body()
        return ok(svc["research"].chat(inv_id, body.get("question"), body.get("history")))

    @app.get("/api/statistics")
    def statistics():
        return ok(svc["csv"].statistics())

    # ------------------------------- ranking ------------------------------- #
    @app.get("/api/rankings/categories")
    def ranking_categories():
        return ok(svc["ranking"].categories())

    @app.get("/api/rankings")
    def rankings_get():
        category = request.args.get("category")
        if not category:
            raise InvalidRequest("Query parameter 'category' is required.")
        return ok(svc["ranking"].rank(category, limit=_int(request.args, "limit", None, 1, 1000)))

    @app.post("/api/rankings")
    def rankings_post():
        body = _body()
        if not body.get("category"):
            raise InvalidRequest("'category' is required.")
        limit = body.get("limit")
        if limit is not None and not (isinstance(limit, int) and limit > 0):
            raise InvalidRequest("'limit' must be a positive integer.")
        weights = body.get("weights")
        if weights is not None and not isinstance(weights, dict):
            raise InvalidRequest("'weights' must be an object.")
        return ok(svc["ranking"].rank(body["category"], weights=weights, limit=limit))

    # ------------------------------ comparison ------------------------------ #
    @app.post("/api/compare")
    def compare():
        body = _body()
        return ok(svc["comparison"].compare(body.get("ids"), explain=_bool(body.get("explain", False))))

    # ------------------------------- AI features ------------------------------ #
    @app.post("/api/ask")
    def ask():
        body = _body()
        return ok(svc["research"].ask(body.get("question"), body.get("history")))

    @app.post("/api/summarize")
    def summarize():
        return ok(svc["research"].summarize(_body().get("investigation_id")))

    @app.get("/api/insights/topics")
    def insight_topics():
        return ok(svc["research"].topics())

    @app.post("/api/insights")
    def insights():
        body = _body()
        return ok(svc["research"].insights(body.get("topic"), body.get("investigation_ids")))

    return app


# --------------------------------------------------------------------------- #
# CORS (uses Flask-CORS when installed, otherwise a minimal equivalent)
# --------------------------------------------------------------------------- #
def _setup_cors(app, config):
    origins = config.CORS_ORIGINS
    try:
        from flask_cors import CORS

        CORS(app, resources={r"/api/*": {"origins": origins}})
        return
    except ImportError:
        pass

    @app.after_request
    def add_cors(resp):
        origin = request.headers.get("Origin")
        if origin and ("*" in origins or origin in origins):
            resp.headers["Access-Control-Allow-Origin"] = "*" if "*" in origins else origin
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
            resp.headers["Vary"] = "Origin"
        return resp


# --------------------------------------------------------------------------- #
# Error handling
# --------------------------------------------------------------------------- #
def _register_errors(app):
    @app.errorhandler(InvalidRequest)
    def bad_request(exc):
        return fail("invalid_request", str(exc), 400)

    @app.errorhandler(InvestigationNotFound)
    def not_found(exc):
        return fail("investigation_not_found", str(exc), 404)

    @app.errorhandler(InvestigationExists)
    def exists(exc):
        return fail("investigation_exists", str(exc), 409)

    @app.errorhandler(DataFileError)
    def bad_file(exc):
        return fail("data_file_error", str(exc), 422)

    @app.errorhandler(AIServiceError)
    def ai_error(exc):
        return fail(exc.code, exc.message, exc.http_status, exc.details)

    @app.errorhandler(404)
    def route_missing(_exc):
        return fail("not_found", "Endpoint not found.", 404)

    @app.errorhandler(405)
    def wrong_method(_exc):
        return fail("method_not_allowed", "Method not allowed for this endpoint.", 405)

    @app.errorhandler(Exception)
    def unexpected(exc):
        if hasattr(exc, "code") and isinstance(exc.code, int):  # other HTTP errors
            return fail("http_error", getattr(exc, "description", str(exc)), exc.code)
        app.logger.exception("Unhandled error")
        return fail("internal_error", "An unexpected error occurred.", 500)


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG", "0") == "1")
