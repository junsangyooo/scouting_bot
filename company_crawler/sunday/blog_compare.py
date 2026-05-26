import json
from pathlib import Path

DATA_PATH = Path("data/sunday/sunday_blog.json")


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

    # 본문(content_hash) 변경 감지. 구 스냅샷에 content_hash가 없으면 excerpt로 폴백.
    updated = []
    for pid in prev_ids & curr_ids:
        prev, curr = prev_map[pid], curr_map[pid]
        if _changed(prev, curr):
            updated.append({
                "id": pid,
                "title": curr["title"],
                "url": curr["url"],
                "before": prev.get("content") or prev.get("excerpt", ""),
                "after": curr.get("content") or curr.get("excerpt", ""),
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


def _changed(prev, curr):
    if "content_hash" in prev and "content_hash" in curr:
        return prev.get("content_hash") != curr.get("content_hash")
    return prev.get("excerpt") != curr.get("excerpt")


def _save(items):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
