import json
from pathlib import Path

DATA_PATH = Path("data/generalist_ai/generalist_blog.json")


def blog_compare(curr_items):
    # 최초 실행
    if not DATA_PATH.exists():
        _save(curr_items)
        return {
            "status": "initialized",
            "added": [],
            "removed": [],
            "updated": [],
        }

    # 이전 데이터 로드
    prev_items = json.loads(DATA_PATH.read_text(encoding="utf-8"))

    prev_map = {p["id"]: p for p in prev_items}
    curr_map = {p["id"]: p for p in curr_items}

    prev_ids = set(prev_map.keys())
    curr_ids = set(curr_map.keys())

    added = [curr_map[i] for i in curr_ids - prev_ids]
    removed = [prev_map[i] for i in prev_ids - curr_ids]

    # excerpt 변경 감지
    updated = []
    for pid in prev_ids & curr_ids:
        if prev_map[pid].get("excerpt") != curr_map[pid].get("excerpt"):
            updated.append({
                "id": pid,
                "title": curr_map[pid]["title"],
                "url": curr_map[pid]["url"],
                "before": prev_map[pid].get("excerpt", ""),
                "after": curr_map[pid].get("excerpt", ""),
            })

    if not added and not removed and not updated:
        return {"status": "checked"}

    _save(curr_items)
    return {
        "status": "updated",
        "added": added,
        "removed": removed,
        "updated": updated,
    }


def _save(items):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
