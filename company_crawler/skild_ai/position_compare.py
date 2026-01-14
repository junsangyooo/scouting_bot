# position_compare.py

import json
from pathlib import Path
from typing import List, Dict

DATA_PATH = Path("data/skild_ai/positions.json")


def position_compare(curr_items: List[Dict]) -> Dict:
    if not DATA_PATH.exists():
        _save(curr_items)
        return {
            "status": "initialized",
            "added": [],
            "removed": [],
            "updated": []
        }

    try:
        prev_items = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        if not isinstance(prev_items, list):
            raise ValueError
    except Exception:
        prev_items = []

    prev_map = {p["id"]: p for p in prev_items}
    curr_map = {p["id"]: p for p in curr_items}

    prev_ids = set(prev_map.keys())
    curr_ids = set(curr_map.keys())

    added_ids = curr_ids - prev_ids
    removed_ids = prev_ids - curr_ids
    common_ids = prev_ids & curr_ids

    added = [curr_map[i] for i in added_ids]
    removed = [prev_map[i] for i in removed_ids]

    updated = []
    for pid in common_ids:
        if prev_map[pid].get("description_hash") != curr_map[pid].get("description_hash"):
            updated.append({
                "id": pid,
                "title": curr_map[pid]["title"],
                "location": curr_map[pid]["location"],
                "before_hash": prev_map[pid]["description_hash"],
                "after_hash": curr_map[pid]["description_hash"],
            })

    _save(curr_items)

    return {
        "status": "updated",
        "added": added,
        "removed": removed,
        "updated": updated
    }


def _save(items: List[Dict]):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
