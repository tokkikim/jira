import base64
import os
import json
import requests
from typing import Any, Dict, List, Optional

JIRA_BASE = os.getenv("JIRA_BASE", "https://mirrorroidkorea.atlassian.net/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")


def _auth_header(
    email: Optional[str] = JIRA_EMAIL, api_token: Optional[str] = JIRA_API_TOKEN
) -> Dict[str, str]:
    if not email or not api_token:
        raise ValueError(
            "Missing credentials. Set JIRA_EMAIL and JIRA_API_TOKEN environment variables."
        )
    token = base64.b64encode(f"{email}:{api_token}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


def create_issue(
    project_key: str,
    summary: str,
    description_text: str,
    issuetype: str = "Bug",
    assignee_account_id: Optional[str] = None,
    labels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    url = f"{JIRA_BASE}/rest/api/3/issue"
    headers = {**_auth_header(), "Content-Type": "application/json"}
    description = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": description_text}],
            }
        ],
    }
    payload: Dict[str, Any] = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issuetype},
            "description": description,
        }
    }
    if assignee_account_id:
        payload["fields"]["assignee"] = {"id": assignee_account_id}
    if labels:
        payload["fields"]["labels"] = labels
    r = requests.post(url, headers=headers, json=payload)
    r.raise_for_status()
    return r.json()


def search_issues(
    jql: str,
    fields: Optional[List[str]] = None,
    start_at: int = 0,
    max_results: int = 50,
) -> Dict[str, Any]:
    url = f"{JIRA_BASE}/rest/api/3/search"
    headers = {**_auth_header(), "Content-Type": "application/json"}
    payload: Dict[str, Any] = {
        "jql": jql,
        "startAt": start_at,
        "maxResults": max_results,
    }
    if fields:
        payload["fields"] = fields
    r = requests.post(url, headers=headers, json=payload)
    r.raise_for_status()
    return r.json()


def add_comment(issue_key: str, body: str) -> Dict[str, Any]:
    url = f"{JIRA_BASE}/rest/api/3/issue/{issue_key}/comment"
    headers = {**_auth_header(), "Content-Type": "application/json"}
    r = requests.post(url, headers=headers, json={"body": body})
    r.raise_for_status()
    return r.json()


def get_transitions(issue_key: str) -> List[Dict[str, Any]]:
    url = f"{JIRA_BASE}/rest/api/3/issue/{issue_key}/transitions"
    r = requests.get(url, headers=_auth_header())
    r.raise_for_status()
    return r.json()["transitions"]


def do_transition(issue_key: str, transition_id: str) -> bool:
    url = f"{JIRA_BASE}/rest/api/3/issue/{issue_key}/transitions"
    headers = {**_auth_header(), "Content-Type": "application/json"}
    r = requests.post(url, headers=headers, json={"transition": {"id": transition_id}})
    r.raise_for_status()
    return r.status_code == 204


def upload_attachment(issue_key: str, filepath: str) -> Dict[str, Any]:
    url = f"{JIRA_BASE}/rest/api/3/issue/{issue_key}/attachments"
    headers = {**_auth_header(), "X-Atlassian-Token": "no-check"}
    with open(filepath, "rb") as f:
        files = {"file": (os.path.basename(filepath), f)}
        r = requests.post(url, headers=headers, files=files)
    r.raise_for_status()
    return r.json()


def get_projects() -> List[Dict[str, Any]]:
    url = f"{JIRA_BASE}/rest/api/3/project"
    r = requests.get(url, headers=_auth_header())
    r.raise_for_status()
    return r.json()


def get_users() -> List[Dict[str, Any]]:
    url = f"{JIRA_BASE}/rest/api/3/users/search"
    headers = _auth_header()
    params = {"maxResults": 1000}
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    users = r.json()
    return [
        {"accountId": u.get("accountId"), "displayName": u.get("displayName")}
        for u in users
        if u.get("accountType") == "atlassian"
    ]


def get_project_members(project_key: str) -> List[Dict[str, Any]]:
    url = f"{JIRA_BASE}/rest/api/3/user/assignable/search"
    headers = _auth_header()
    params = {"project": project_key, "maxResults": 1000}
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    members = r.json()
    return [
        {"accountId": m.get("accountId"), "displayName": m.get("displayName")}
        for m in members
        if m.get("accountType") == "atlassian"
    ]
