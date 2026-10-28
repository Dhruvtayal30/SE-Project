"""Flask HTTP layer: request parsing, JSON errors, example programs, optional static frontend."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from flask import Blueprint, Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException, MethodNotAllowed, NotFound

from .analyzer import analyze_source
from .errors import AnalysisError, RequestError
from .serialize import API_VERSION
from .validation import MAX_SOURCE_CHARS, validate_request

log = logging.getLogger("cfg_analyzer")
ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = ROOT / "examples"

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    return jsonify({"ok": True, "api_version": API_VERSION})


@bp.post("/analyze")
def analyze():
    payload = request.get_json(silent=True)
    if payload is None:
        raise RequestError("Request body must be valid JSON with Content-Type: application/json.", code="MALFORMED_JSON")
    result = analyze_source(validate_request(payload))
    return jsonify(result)


@bp.get("/examples")
def examples():
    manifest = EXAMPLES_DIR / "manifest.json"
    if not manifest.is_file():
        return jsonify({"ok": True, "examples": []})
    items = []
    for item in json.loads(manifest.read_text(encoding="utf-8")):
        item = dict(item)
        item["source"] = (EXAMPLES_DIR / item["file"]).read_text(encoding="utf-8")
        items.append(item)
    return jsonify({"ok": True, "examples": items})


def create_app(static_dir: Path | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 2 * MAX_SOURCE_CHARS + 4096
    app.register_blueprint(bp)

    @app.errorhandler(AnalysisError)
    def handle_analysis(exc: AnalysisError):
        return jsonify(exc.to_dict()), exc.status

    @app.errorhandler(HTTPException)
    def handle_http(exc: HTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 413: "SOURCE_TOO_LARGE", 415: "UNSUPPORTED_MEDIA_TYPE"}.get(
            exc.code or 500, "HTTP_ERROR")
        return jsonify({"ok": False, "error": {"code": code, "message": exc.description or exc.name}}), exc.code or 500

    @app.errorhandler(Exception)
    def handle_unexpected(exc: Exception):
        log.exception("Unexpected error while handling %s", request.path)
        return jsonify({"ok": False, "error": {"code": "INTERNAL_ERROR",
                                               "message": "Unexpected internal error. The analysis was not completed."}}), 500

    dist = static_dir or ROOT / "frontend" / "dist"
    if dist.is_dir():
        @app.get("/")
        def index():
            return send_from_directory(dist, "index.html")

        @app.get("/<path:name>")
        def assets(name: str):
            if name.startswith("api/"):          # the static catch-all must not hide API 404/405 behaviour
                api_paths = {r.rule: r.methods for r in app.url_map.iter_rules() if r.endpoint.startswith("api.")}
                if "/" + name in api_paths:
                    raise MethodNotAllowed(sorted((api_paths["/" + name] or set()) - {"HEAD", "OPTIONS"}))
                raise NotFound()
            return send_from_directory(dist, name)

    return app
