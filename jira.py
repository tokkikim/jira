from dotenv import load_dotenv

load_dotenv()

import os
from app.services.jira_client import (
    create_issue,
    search_issues,
    add_comment,
    get_transitions,
    do_transition,
    upload_attachment,
    get_projects,
    get_users,
    get_project_members,
)
from app.services.overlay_store import (
    OverlayStore,
    set_overlay,
    set_overlay_dates,
    set_overlay_color,
    set_overlay_hidden,
)
from app.controllers.timeline_controller import (
    search_issues_with_overlays,
    build_timeline_view,
)
from app.views.exporters import export_timeline_json, export_timeline_html

__all__ = [
    # services
    "create_issue",
    "search_issues",
    "add_comment",
    "get_transitions",
    "do_transition",
    "upload_attachment",
    "get_projects",
    "get_users",
    "get_project_members",
    # overlay
    "OverlayStore",
    "set_overlay",
    "set_overlay_dates",
    "set_overlay_color",
    "set_overlay_hidden",
    # controller
    "search_issues_with_overlays",
    "build_timeline_view",
    # views
    "export_timeline_json",
    "export_timeline_html",
]

if __name__ == "__main__" and os.getenv("RUN_TIMELINE_DEMO") == "1":
    projects = os.getenv("JIRA_PROJECTS", "SR").split(",")
    ok = export_timeline_html(
        projects, outfile="timeline.html", group_by=os.getenv("GROUP_BY", "project")
    )
    print("Exported timeline.html" if ok else "Failed to export timeline.html")
