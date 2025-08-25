from flask import Flask, request, jsonify, Response, render_template
from typing import Any, Dict, List, Optional
from app.controllers.timeline_controller import (
    search_issues_with_overlays,
    build_timeline_view,
)

# from app.services.jira_client import get_projects
from datetime import datetime

# Logging additions
import logging, time, os
from flask import g

app = Flask(__name__)

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def _setup_logging() -> None:
    level = getattr(logging, LOG_LEVEL, logging.INFO)
    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    # Isolate app logger (do not touch root) to avoid recursion with external middlewares
    app.logger.handlers.clear()
    app_handler = logging.StreamHandler()
    app_handler.setFormatter(logging.Formatter(fmt, datefmt))
    app.logger.addHandler(app_handler)
    app.logger.setLevel(level)
    app.logger.propagate = False

    # Also isolate werkzeug logger
    wz = logging.getLogger("werkzeug")
    wz.handlers.clear()
    wz_handler = logging.StreamHandler()
    wz_handler.setFormatter(logging.Formatter(fmt, datefmt))
    wz.addHandler(wz_handler)
    wz.setLevel(level)
    wz.propagate = False


_setup_logging()


# Per-request logging
@app.before_request
def _log_request_start() -> None:
    g._t0 = time.time()
    app.logger.info(
        "REQ %s %s args=%s ip=%s ua=%s",
        request.method,
        request.path,
        dict(request.args),
        request.headers.get("X-Forwarded-For") or request.remote_addr,
        request.headers.get("User-Agent", "-"),
    )


@app.after_request
def _log_request_end(response):
    try:
        dur_ms = (time.time() - getattr(g, "_t0", time.time())) * 1000.0
    except Exception:
        dur_ms = -1
    app.logger.info(
        "RES %s %s status=%s len=%s dur=%.1fms",
        request.method,
        request.path,
        response.status_code,
        (
            response.calculate_content_length()
            if hasattr(response, "calculate_content_length")
            else "-"
        ),
        dur_ms,
    )
    return response


@app.errorhandler(404)
def not_found_error(error):
    return (
        render_template(
            "error.html",
            error_code=404,
            error_message="페이지를 찾을 수 없습니다",
            error_description="요청하신 페이지가 존재하지 않습니다.",
        ),
        404,
    )


@app.errorhandler(500)
def internal_error(error):
    return (
        render_template(
            "error.html",
            error_code=500,
            error_message="서버 오류",
            error_description="서버에서 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        ),
        500,
    )


@app.errorhandler(Exception)
def _log_exception(e):
    app.logger.exception("Unhandled error at %s %s", request.method, request.path)
    return (
        render_template(
            "error.html",
            error_code=500,
            error_message="예상치 못한 오류",
            error_description="예상치 못한 오류가 발생했습니다.",
        ),
        500,
    )


def _parse_iso_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        if "T" in s:
            if s.endswith("Z"):
                fmts = ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"]
                for f in fmts:
                    try:
                        return datetime.strptime(s, f)
                    except Exception:
                        pass
                return None
            s2 = s
            if "+" in s:
                s2 = s.split("+")[0]
            elif "-" in s[10:]:
                s2 = s[:19]
            fmts = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"]
            for f in fmts:
                try:
                    return datetime.strptime(s2, f)
                except Exception:
                    pass
            return None
        else:
            return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None


def _build_view_for_request(args) -> Dict[str, Any]:
    projects_param = args.get("projects") or args.get("project")
    if projects_param:
        project_keys = [p.strip() for p in projects_param.split(",") if p.strip()]
    else:
        import os

        project_keys = [
            p.strip() for p in os.getenv("JIRA_PROJECTS", "SR").split(",") if p.strip()
        ]
    if not project_keys:
        return {"groups": [], "items": []}

    group_by = args.get("group_by", "project")
    user_owner = args.get("user_owner")
    from_date = args.get("from_date")
    to_date = args.get("to_date")

    pj = ",".join(project_keys)
    jql = f"project in ({pj})"
    result = search_issues_with_overlays(jql, user_owner=user_owner, max_results=1000)
    view = build_timeline_view(result, group_by=group_by)

    fd = _parse_iso_date(from_date) if from_date else None
    td = _parse_iso_date(to_date) if to_date else None
    if fd or td:
        filtered: List[Dict[str, Any]] = []
        for it in view["items"]:
            s = _parse_iso_date(it.get("start"))
            e = _parse_iso_date(it.get("end")) or s
            if not s and not e:
                continue
            ok = True
            if fd and e and e.date() < fd.date():
                ok = False
            if td and s and s.date() > td.date():
                ok = False
            if ok:
                filtered.append(it)
        view["items"] = filtered

    return view


@app.get("/api/timeline")
def api_timeline():
    try:
        view = _build_view_for_request(request.args)
        return jsonify(view)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/projects")
def api_projects():
    try:
        # 임시 샘플 프로젝트 데이터
        sample_projects = [
            {
                "key": "SR",
                "name": "Sample Project",
                "projectTypeKey": "software",
                "simplified": False,
            },
            {
                "key": "AB",
                "name": "Another Project",
                "projectTypeKey": "software",
                "simplified": False,
            },
            {
                "key": "TEST",
                "name": "Test Project",
                "projectTypeKey": "software",
                "simplified": False,
            },
        ]
        return jsonify({"projects": sample_projects})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/docs")
def api_docs():
    return render_template("api_docs.html")


@app.get("/api/sample")
def api_sample():
    """테스트용 샘플 데이터를 반환합니다."""
    sample_data = {
        "groups": [
            {"id": "SR", "title": "SR · Sample Project"},
            {"id": "AB", "title": "AB · Another Project"},
        ],
        "items": [
            {
                "id": "SR-100",
                "group": "SR",
                "content": "샘플 이슈 1",
                "start": "2024-01-15",
                "end": "2024-01-20",
                "color": "#ff6b6b",
            },
            {
                "id": "SR-101",
                "group": "SR",
                "content": "샘플 이슈 2",
                "start": "2024-01-18",
                "end": "2024-01-25",
                "color": "#4ecdc4",
            },
            {
                "id": "AB-200",
                "group": "AB",
                "content": "다른 프로젝트 이슈",
                "start": "2024-01-10",
                "end": "2024-01-30",
                "color": "#45b7d1",
            },
        ],
    }
    return jsonify(sample_data)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5001"))
    host = os.getenv("HOST", "0.0.0.0")
    app.logger.info(
        "Starting Flask server at http://%s:%s (LOG_LEVEL=%s)", host, port, LOG_LEVEL
    )
    app.run(host=host, port=port, debug=True)
