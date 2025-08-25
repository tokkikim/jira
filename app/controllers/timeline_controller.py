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

    # 프로젝트별로 이슈들을 분류
    project_issues: Dict[str, List[Dict[str, Any]]] = {}

    for issue in issues:
        f = issue.get("fields", {})
        ov = issue.get("overlay", {})
        if ov.get("hidden"):
            continue

        # 프로젝트 정보
        proj = f.get("project") or {}
        project_key = proj.get("key", "UNKNOWN")

        # 이슈 타입별로 분류
        issue_type = (f.get("issuetype") or {}).get("name", "Task")

        # 한국어 이슈 타입을 영어로 매핑
        issue_type_mapping = {
            "서버": "Server",
            "버그": "Bug",
            "디자인": "Design",
            "기획": "Planning",
            "하위업무": "Task",
            "스토리": "Story",
            "에픽": "Epic",
            "QA": "QA",
            "클라": "Client",
        }

        # 매핑된 타입 사용
        mapped_issue_type = issue_type_mapping.get(issue_type, issue_type)

        # 에픽 정보 가져오기 (일단 None으로 설정, 나중에 실제 필드 확인 후 수정)
        epic_key = None
        epic_summary = None
        if mapped_issue_type != "Epic":
            # 에픽 링크 필드에서 에픽 정보 가져오기 (실제 필드명 확인 필요)
            epic_link = f.get("customfield_10014")  # 에픽 링크 필드
            if epic_link and isinstance(epic_link, dict):
                epic_key = epic_link.get("key")
                epic_summary = epic_link.get("summary")

        # 프로젝트별로 이슈 분류
        if project_key not in project_issues:
            project_issues[project_key] = []
        project_issues[project_key].append(
            {
                "issue": issue,
                "issue_type": mapped_issue_type,
                "summary": f.get("summary", ""),
                "key": issue.get("key", ""),
                "epic_key": epic_key,
                "epic_summary": epic_summary,
            }
        )

    # 각 프로젝트별로 계층 구조 생성
    for project_key, project_issue_list in project_issues.items():
        # 에픽별로 이슈 분류
        epic_issues: Dict[str, List[Dict[str, Any]]] = {}
        non_epic_issues: List[Dict[str, Any]] = []

        for item in project_issue_list:
            if item["issue_type"] == "Epic":
                # 에픽 자체는 별도 그룹으로
                epic_key = item["key"]
                if epic_key not in epic_issues:
                    epic_issues[epic_key] = []
            else:
                # 에픽이 있는 이슈와 없는 이슈 분류
                if item["epic_key"]:
                    if item["epic_key"] not in epic_issues:
                        epic_issues[item["epic_key"]] = []
                    epic_issues[item["epic_key"]].append(item)
                else:
                    non_epic_issues.append(item)

        # 1. 프로젝트 그룹 생성
        project_group_id = f"{project_key}_PROJECT"
        groups[project_group_id] = {
            "id": project_group_id,
            "title": f"{project_key}",
            "content": f"{project_key}",
            "project": project_key,
            "level": 1,
            "order": 0,
        }

        # 2. 에픽 그룹들 생성
        epic_order = 1
        for epic_key, epic_item_list in epic_issues.items():
            # 에픽 정보 찾기
            epic_info = None
            for item in epic_item_list:
                if item["key"] == epic_key:
                    epic_info = item
                    break

            if epic_info:
                epic_group_id = f"{project_key}_EPIC_{epic_key}"
                groups[epic_group_id] = {
                    "id": epic_group_id,
                    "title": f"{project_key} | {epic_info['summary']}",
                    "content": f"{project_key} | {epic_info['summary']}",
                    "project": project_key,
                    "epic_key": epic_key,
                    "level": 2,
                    "order": epic_order,
                }
                epic_order += 1

                # 3. 에픽 하위 이슈 타입별 그룹 생성
                type_issues: Dict[str, List[Dict[str, Any]]] = {}
                for item in epic_item_list:
                    if item["key"] != epic_key:  # 에픽 자체는 제외
                        issue_type = item["issue_type"]
                        if issue_type not in type_issues:
                            type_issues[issue_type] = []
                        type_issues[issue_type].append(item)

                # 이슈 타입별 그룹 생성 (에픽 하위)
                for issue_type, type_item_list in type_issues.items():
                    if issue_type != "Task":  # 하위업무는 별도 처리
                        type_group_id = f"{project_key}_EPIC_{epic_key}_{issue_type}"
                        type_kr = {
                            "Story": "스토리",
                            "Bug": "버그",
                            "Design": "디자인",
                            "Planning": "기획",
                            "QA": "QA",
                            "Server": "서버",
                            "Client": "클라",
                        }.get(issue_type, issue_type)

                        groups[type_group_id] = {
                            "id": type_group_id,
                            "title": f"{project_key} | {epic_info['summary']} | {type_kr}",
                            "content": f"{project_key} | {epic_info['summary']} | {type_kr}",
                            "project": project_key,
                            "epic_key": epic_key,
                            "issue_type": issue_type,
                            "level": 3,
                            "order": epic_order * 100
                            + list(type_issues.keys()).index(issue_type),
                        }

                        # 4. 하위업무 그룹 생성 (이슈 타입 하위)
                        task_items = [
                            item
                            for item in type_item_list
                            if item["issue_type"] == "Task"
                        ]
                        if task_items:
                            task_group_id = (
                                f"{project_key}_EPIC_{epic_key}_{issue_type}_TASK"
                            )
                            groups[task_group_id] = {
                                "id": task_group_id,
                                "title": f"{project_key} | {epic_info['summary']} | {type_kr} | 하위업무",
                                "content": f"{project_key} | {epic_info['summary']} | {type_kr} | 하위업무",
                                "project": project_key,
                                "epic_key": epic_key,
                                "issue_type": issue_type,
                                "level": 4,
                                "order": epic_order * 1000
                                + list(type_issues.keys()).index(issue_type) * 10
                                + 1,
                            }

        # 3. 에픽이 없는 이슈들의 그룹 생성
        if non_epic_issues:
            type_issues: Dict[str, List[Dict[str, Any]]] = {}
            for item in non_epic_issues:
                issue_type = item["issue_type"]
                if issue_type not in type_issues:
                    type_issues[issue_type] = []
                type_issues[issue_type].append(item)

            # 이슈 타입별 그룹 생성 (프로젝트 직접 하위)
            for issue_type, type_item_list in type_issues.items():
                if issue_type != "Task":  # 하위업무는 별도 처리
                    type_group_id = f"{project_key}_DIRECT_{issue_type}"
                    type_kr = {
                        "Story": "스토리",
                        "Bug": "버그",
                        "Design": "디자인",
                        "Planning": "기획",
                        "QA": "QA",
                        "Server": "서버",
                        "Client": "클라",
                    }.get(issue_type, issue_type)

                    groups[type_group_id] = {
                        "id": type_group_id,
                        "title": f"{project_key} | {type_kr}",
                        "content": f"{project_key} | {type_kr}",
                        "project": project_key,
                        "issue_type": issue_type,
                        "level": 3,
                        "order": 1000 + list(type_issues.keys()).index(issue_type),
                    }

                    # 4. 하위업무 그룹 생성 (프로젝트 직접 하위)
                    task_items = [
                        item for item in type_item_list if item["issue_type"] == "Task"
                    ]
                    if task_items:
                        task_group_id = f"{project_key}_DIRECT_{issue_type}_TASK"
                        groups[task_group_id] = {
                            "id": task_group_id,
                            "title": f"{project_key} | {type_kr} | 하위업무",
                            "content": f"{project_key} | {type_kr} | 하위업무",
                            "project": project_key,
                            "issue_type": issue_type,
                            "level": 4,
                            "order": 10000
                            + list(type_issues.keys()).index(issue_type) * 10
                            + 1,
                        }

        # 모든 이슈를 아이템으로 추가
        all_items = []
        for epic_key, epic_item_list in epic_issues.items():
            all_items.extend(epic_item_list)
        all_items.extend(non_epic_issues)

        for item in all_items:
            issue = item["issue"]
            f = issue.get("fields", {})
            ov = issue.get("overlay", {})

            start, end = _derive_dates(issue)
            if not start and not end:
                continue

            status = (f.get("status") or {}).get("name")
            priority = (f.get("priority") or {}).get("name")

            # 제목만 표시 (이슈키 제거)
            summary = f.get("summary", "")
            content = summary if summary else issue.get("key", "")

            # 그룹 ID 결정
            group_id = None
            if item["issue_type"] == "Epic":
                group_id = f"{project_key}_EPIC_{item['key']}"
            elif item["epic_key"]:
                if item["issue_type"] == "Task":
                    # 하위업무는 상위 이슈 타입 그룹에 배치
                    parent_type = None
                    for other_item in epic_issues[item["epic_key"]]:
                        if (
                            other_item["key"] != item["epic_key"]
                            and other_item["issue_type"] != "Task"
                        ):
                            parent_type = other_item["issue_type"]
                            break
                    if parent_type:
                        group_id = (
                            f"{project_key}_EPIC_{item['epic_key']}_{parent_type}_TASK"
                        )
                    else:
                        group_id = f"{project_key}_EPIC_{item['epic_key']}"
                else:
                    group_id = (
                        f"{project_key}_EPIC_{item['epic_key']}_{item['issue_type']}"
                    )
            else:
                if item["issue_type"] == "Task":
                    # 하위업무는 상위 이슈 타입 그룹에 배치
                    parent_type = None
                    for other_item in non_epic_issues:
                        if (
                            other_item["key"] != item["key"]
                            and other_item["issue_type"] != "Task"
                        ):
                            parent_type = other_item["issue_type"]
                            break
                    if parent_type:
                        group_id = f"{project_key}_DIRECT_{parent_type}_TASK"
                    else:
                        group_id = f"{project_key}_DIRECT_{item['issue_type']}"
                else:
                    group_id = f"{project_key}_DIRECT_{item['issue_type']}"

            # 이슈 타입별 색상 설정
            color = ov.get("color")
            if not color:
                if item["issue_type"] == "Bug":
                    color = "#ef4444"  # 빨간색
                elif item["issue_type"] == "Task":
                    color = "#3b82f6"  # 파란색
                elif item["issue_type"] == "Story":
                    color = "#10b981"  # 초록색
                elif item["issue_type"] == "Epic":
                    color = "#8b5cf6"  # 보라색
                else:
                    color = "#f59e0b"  # 주황색

            items.append(
                {
                    "id": issue.get("key"),
                    "group": group_id,
                    "content": content,
                    "title": summary,  # 툴팁으로 전체 제목 표시
                    "start": start,
                    "end": end,
                    "color": color,
                    "status": status,
                    "priority": priority,
                    "issue_type": item["issue_type"],
                    "url": issue.get("self"),
                    "overlay": ov,
                }
            )

    # 그룹을 순서대로 정렬
    sorted_groups = sorted(
        groups.values(), key=lambda x: (x["project"], x.get("order", 999))
    )

    return {"groups": sorted_groups, "items": items}
