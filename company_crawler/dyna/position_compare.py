# position_compare.py

import json
from pathlib import Path
from typing import List, Dict

DATA_PATH = Path("data/dyna/dyna_positions.json")


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
                "compensation": curr_map[pid].get("compensation", ""),
                "before_hash": prev_map[pid].get("description_hash", ""),
                "after_hash": curr_map[pid].get("description_hash", ""),
            })

    if not added and not removed and not updated:
        return {
            "status": "checked"
        }

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


if __name__ == "__main__":
    from position_crawler import position_crawler

    print("[INFO] Crawling DYNA positions...")
    positions = position_crawler()

    print(f"[INFO] Comparing {len(positions)} positions...")
    result = position_compare(positions)

    print(f"\n[RESULT] Status: {result['status']}")

    if result['status'] == 'initialized':
        print(f"  Initialized with {len(positions)} positions")
    elif result['status'] == 'updated':
        if result.get('added'):
            print(f"\n  Added ({len(result['added'])}):")
            for p in result['added']:
                print(f"    + {p['title']} ({p['location']})")
        if result.get('removed'):
            print(f"\n  Removed ({len(result['removed'])}):")
            for p in result['removed']:
                print(f"    - {p['title']} ({p['location']})")
        if result.get('updated'):
            print(f"\n  Updated ({len(result['updated'])}):")
            for p in result['updated']:
                print(f"    ~ {p['title']} ({p['location']})")
    else:
        print("  No changes detected")
