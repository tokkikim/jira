from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from app.services.jira_client import search_issues
from app.services.overlay_store import OverlayStore


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


def _derive_dates(issue: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    f = issue.get("fields", {})
    ov = issue.get("overlay", {})
    start = ov.get("startDate")
    end = ov.get("dueDate") or ov.get("endDate")
    if not start:
        created = f.get("created")
        dt = _parse_iso_date(created)
        if dt:
            start = dt.date().isoformat()
    if not end:
        due = f.get("duedate")
        end = due or start
    return start, end


def search_issues_with_overlays(
    jql: str,
    *,
    user_owner: Optional[str] = None,
    fields: Optional[List[str]] = None,
    start_at: int = 0,
    max_results: int = 50,
) -> Dict[str, Any]:
    result = search_issues(
        jql, fields=fields, start_at=start_at, max_results=max_results
    )
    issue_keys = [i.get("key") for i in result.get("issues", []) if i.get("key")]
    store = OverlayStore()
    overlays = store.get_overlays_merged(issue_keys=issue_keys, user_owner=user_owner)
    issues = []
    for issue in result.get("issues", []):
        i = dict(issue)
        key = i.get("key")
        if key and key in overlays:
            i["overlay"] = overlays[key]
        issues.append(i)
    out = dict(result)
    out["issues"] = issues
    return out


def build_timeline_view(
    issues_result: Dict[str, Any], *, group_by: str = "project"
) -> Dict[str, Any]:
    issues = issues_result.get("issues", []) if issues_result else []
    groups: Dict[str, Dict[str, Any]] = {}
    items: List[Dict[str, Any]] = []

    for issue in issues:
        f = issue.get("fields", {})
        ov = issue.get("overlay", {})
        if ov.get("hidden"):
            continue
        if group_by == "assignee":
            assignee = f.get("assignee") or {}
            gid = assignee.get("accountId") or "__unassigned__"
            gtitle = assignee.get("displayName") or "Unassigned"
        else:
            proj = f.get("project") or {}
            gid = proj.get("key") or "__unknown__"
            gtitle = f"{proj.get('key', '?')} · {proj.get('name', 'Unknown')}"
        if gid not in groups:
            groups[gid] = {"id": gid, "title": gtitle}

        start, end = _derive_dates(issue)
        if not start and not end:
            continue

        status = (f.get("status") or {}).get("name")
        priority = (f.get("priority") or {}).get("name")

        items.append(
            {
                "id": issue.get("key"),
                "group": gid,
                "content": f.get("summary"),
                "start": start,
                "end": end,
                "color": ov.get("color"),
                "status": status,
                "priority": priority,
                "url": issue.get("self"),
                "overlay": ov,
            }
        )

    return {"groups": list(groups.values()), "items": items}
