import json
from typing import Any, Dict, List, Optional

from app.controllers.timeline_controller import (
    build_timeline_view,
    search_issues_with_overlays,
)
from app.services.file_utils import save_json_to_file


def export_timeline_json(
    project_keys: List[str],
    *,
    outfile: str = "timeline.json",
    user_owner: Optional[str] = None,
    group_by: str = "project",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> bool:
    if not project_keys:
        raise ValueError("project_keys required")
    pj = ",".join(project_keys)
    jql = f"project in ({pj})"
    result = search_issues_with_overlays(jql, user_owner=user_owner, max_results=1000)
    view = build_timeline_view(result, group_by=group_by)

    # client-side filter by date range (overlap)
    from app.controllers.timeline_controller import _parse_iso_date

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

    return save_json_to_file(view, outfile)


def export_timeline_html(
    project_keys: List[str],
    *,
    outfile: str = "timeline.html",
    user_owner: Optional[str] = None,
    group_by: str = "project",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> bool:
    ok = export_timeline_json(
        project_keys,
        outfile="timeline.json.tmp",
        user_owner=user_owner,
        group_by=group_by,
        from_date=from_date,
        to_date=to_date,
    )
    if not ok:
        return False
    with open("timeline.json.tmp", "r", encoding="utf-8") as f:
        data = json.load(f)

    for it in data.get("items", []):
        color = it.get("color")
        if color:
            it["style"] = (
                f"background-color: {color}; border-color: {color}; color: #111;"
            )

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
    #app { height: 100vh; }
    .vis-item.vis-range { border-radius: 6px; }
    .header { padding: 10px 12px; border-bottom: 1px solid #e5e7eb; display:flex; align-items:center; gap:12px; }
    .badge { font-size:12px; background:#eef2ff; color:#3730a3; padding:2px 8px; border-radius:999px; }
  </style>
</head>
<body>
  <div class=\"header\">
    <strong>Read-only Timeline</strong>
    <span class=\"badge\">Local overlays applied (not written to JIRA)</span>
  </div>
  <div id=\"app\"></div>
  <script src=\"https://unpkg.com/vis-data@latest/peer/umd/vis-data.min.js\"></script>
  <script src=\"https://unpkg.com/vis-timeline@latest/peer/umd/vis-timeline-graph2d.min.js\"></script>
  <script>
    const data = __DATA__;
    const container = document.getElementById('app');
    const items = new vis.DataSet(data.items.map(it => ({
      id: it.id,
      group: it.group,
      content: it.content,
      start: it.start ? new Date(it.start) : null,
      end: it.end ? new Date(it.end + 'T23:59:59') : null,
      style: it.style || ''
    })));
    const groups = new vis.DataSet(data.groups);

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
  </script>
</body>
</html>
"""
    html = html.replace("__DATA__", json.dumps(data).replace("</", "<\\/"))
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(html)
    try:
        import os

        os.remove("timeline.json.tmp")
    except Exception:
        pass
    return True
