import json
from pathlib import Path
from typing import List, Dict

DATA_PATH = Path("data/skild_ai/blog.json")

def blog_compare(curr_items):
    if not DATA_PATH.exists():
        _save(curr_items)
        return {
            "status": "initialized",
            "added": [],
            "removed": [],
            "updated": []
        }

    prev_items = json.loads(DATA_PATH.read_text(encoding="utf-8"))

    prev_map = {p["id"]: p for p in prev_items}
    curr_map = {p["id"]: p for p in curr_items}

    prev_ids = set(prev_map.keys())
    curr_ids = set(curr_map.keys())

    added_ids = curr_ids - prev_ids
    removed_ids = prev_ids - curr_ids

    added = [curr_ids[i] for i in added_ids]
    removed = [prev_ids[i] for i in removed_ids]

    updated = []
    common_ids = prev_ids & curr_ids

    for pid in common_ids:
        if prev_map[pid].get("excerpt") != curr_map[pid].get("excerpt"):
            updated.append({
                "id": pid,
                "title": curr_map[pid]["title"],
                "url": curr_map[pid]["url"],
                "before": prev_map[pid].get("excerpt", ""),
                "after": curr_map[pid].get("excerpt", "")
            })

    _save(curr_items)
    return {
        "status": "updated",
        "added": added,
        "removed": removed,
        "updated": updated
    }


def _save(items):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
