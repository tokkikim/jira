import json
from typing import Any


def save_json_to_file(data: Any, filename: str) -> bool:
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"JSON 파일 저장 실패: {e}")
        return False
