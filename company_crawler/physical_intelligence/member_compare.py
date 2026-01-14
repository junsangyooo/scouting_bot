import json
from pathlib import Path

memberPath = Path("data/physical_intelligence/members.json")

def member_compare(curr_members):
    curr_set = set(curr_members)

    if not memberPath.exists():
        memberPath.parent.mkdir(parents=True, exist_ok=True)
        _save_members(curr_members)
        return {
            "status": "initialized",
            "added": [],
            "removed": []
        }
    
    with open(memberPath, "r", encoding="utf-8") as f:
        prev_members = json.load(f)

    prev_set = set(prev_members)

    added = sorted(list(curr_set - prev_set))
    removed = sorted(list(prev_set - curr_set))

    _save_members(curr_members)

    return {
        "status": "updated",
        "added": added,
        "removed": removed
    }

def _save_members(members):
    with open(memberPath, "w", encoding="utf-8") as f:
        json.dump(
            members,
            f,
            ensure_ascii=False,
            indent=2
        )