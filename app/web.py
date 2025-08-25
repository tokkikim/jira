from flask import Flask, request, jsonify, Response
from typing import Any, Dict, List, Optional
from app.controllers.timeline_controller import (
    search_issues_with_overlays,
    build_timeline_view,
)
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


@app.errorhandler(Exception)
def _log_exception(e):
    app.logger.exception("Unhandled error at %s %s", request.method, request.path)
    return jsonify({"error": str(e)}), 500


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


@app.get("/")
def index():
    # Minimal HTML page with controls and timeline rendering
    html = """
<!doctype html>
<html lang=\"ko\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Timeline</title>
  <link rel=\"stylesheet\" href=\"https://unpkg.com/vis-timeline@latest/styles/vis-timeline-graph2d.min.css\" />
  <style>
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif; }
    header { padding: 10px 12px; border-bottom: 1px solid #e5e7eb; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    label { font-size: 12px; color: #374151; }
    input, select, button { font-size: 14px; padding: 6px 8px; }
    #app { height: calc(100vh - 58px); }
    .vis-item.vis-range { border-radius: 6px; }
  </style>
</head>
<body>
  <header>
    <label>Projects <input id=\"projects\" placeholder=\"SR,AB\" /></label>
    <label>Group <select id=\"group_by\"><option value=\"project\">Project</option><option value=\"assignee\">Assignee</option></select></label>
    <label>From <input id=\"from_date\" type=\"date\" /></label>
    <label>To <input id=\"to_date\" type=\"date\" /></label>
    <button id=\"load\">Load</button>
    <span style=\"margin-left:auto;font-size:12px;color:#6b7280;\">Read-only · Local overlays</span>
  </header>
  <div id=\"app\"></div>

  <script src=\"https://unpkg.com/vis-data@latest/peer/umd/vis-data.min.js\"></script>
  <script src=\"https://unpkg.com/vis-timeline@latest/peer/umd/vis-timeline-graph2d.min.js\"></script>
  <script>
    const qs = new URLSearchParams(window.location.search);
    document.getElementById('projects').value = qs.get('projects') || (qs.get('project') || '');
    document.getElementById('group_by').value = qs.get('group_by') || 'project';
    if (qs.get('from_date')) document.getElementById('from_date').value = qs.get('from_date');
    if (qs.get('to_date')) document.getElementById('to_date').value = qs.get('to_date');

    async function load() {
      const projects = document.getElementById('projects').value.trim();
      const group_by = document.getElementById('group_by').value;
      const from_date = document.getElementById('from_date').value;
      const to_date = document.getElementById('to_date').value;
      const url = new URL('/api/timeline', window.location.origin);
      if (projects) url.searchParams.set('projects', projects);
      url.searchParams.set('group_by', group_by);
      if (from_date) url.searchParams.set('from_date', from_date);
      if (to_date) url.searchParams.set('to_date', to_date);
      const res = await fetch(url);
      const data = await res.json();
      renderTimeline(data);
      const newQs = new URLSearchParams();
      if (projects) newQs.set('projects', projects);
      newQs.set('group_by', group_by);
      if (from_date) newQs.set('from_date', from_date);
      if (to_date) newQs.set('to_date', to_date);
      history.replaceState(null, '', `/?${newQs.toString()}`);
    }

    function renderTimeline(data) {
      const container = document.getElementById('app');
      container.innerHTML = '';
      const items = new vis.DataSet((data.items || []).map(it => ({
        id: it.id,
        group: it.group,
        content: it.content,
        start: it.start ? new Date(it.start) : null,
        end: it.end ? new Date(it.end + 'T23:59:59') : null,
        style: it.color ? `background-color:${it.color};border-color:${it.color};color:#111;` : ''
      })));
      const groups = new vis.DataSet(data.groups || []);
      const today = new Date();
      const startWindow = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 14);
      const endWindow = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 45);
      const timeline = new vis.Timeline(container, items, groups, {
        stack: true,
        orientation: 'top',
        multiselect: false,
        showCurrentTime: true,
        zoomKey: 'ctrlKey',
        margin: { item: 6, axis: 12 },
        min: startWindow,
        max: endWindow,
        timeAxis: { scale: 'day', step: 1 },
        zoomMin: 1000 * 60 * 60 * 24,
        zoomMax: 1000 * 60 * 60 * 24 * 365
      });
      timeline.addCustomTime(new Date(), 'now');
    }

    document.getElementById('load').addEventListener('click', load);
    load();
  </script>
</body>
</html>
"""
    return Response(html, mimetype="text/html")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5001"))
    host = os.getenv("HOST", "0.0.0.0")
    app.logger.info(
        "Starting Flask server at http://%s:%s (LOG_LEVEL=%s)", host, port, LOG_LEVEL
    )
    app.run(host=host, port=port, debug=True)
