"""
Unified comparison utilities for snapshot data.
Used by both daily crawler (yesterday vs today) and /analyze command (date A vs date B).
"""

import json
import hashlib
from pathlib import Path


def compare_positions(prev_data, curr_data):
    """
    Compare two position snapshots.

    Args:
        prev_data: list[dict] - previous positions
        curr_data: list[dict] - current positions

    Returns:
        dict with status, added, removed, updated
    """
    # Ensure description_hash exists
    for pos in curr_data:
        if "description_hash" not in pos:
            pos["description_hash"] = _hash_text(pos.get("description", ""))
    for pos in prev_data:
        if "description_hash" not in pos:
            pos["description_hash"] = _hash_text(pos.get("description", ""))

    prev_map = {p["id"]: p for p in prev_data}
    curr_map = {p["id"]: p for p in curr_data}

    prev_ids = set(prev_map.keys())
    curr_ids = set(curr_map.keys())

    added = [curr_map[i] for i in curr_ids - prev_ids]
    removed = [prev_map[i] for i in prev_ids - curr_ids]

    updated = []
    for pid in prev_ids & curr_ids:
        if prev_map[pid].get("description_hash") != curr_map[pid].get("description_hash"):
            updated.append({
                "id": pid,
                "title": curr_map[pid]["title"],
                "url": curr_map[pid].get("url", ""),
                "before": prev_map[pid].get("description", ""),
                "after": curr_map[pid].get("description", ""),
            })

    if not added and not removed and not updated:
        return {"status": "checked"}

    return {
        "status": "updated",
        "added": added,
        "removed": removed,
        "updated": updated,
    }


def compare_blogs(prev_data, curr_data):
    """
    Compare two blog snapshots.

    Args:
        prev_data: list[dict] - previous blogs
        curr_data: list[dict] - current blogs

    Returns:
        dict with status, added, removed, updated
    """
    prev_map = {p["id"]: p for p in prev_data}
    curr_map = {p["id"]: p for p in curr_data}

    prev_ids = set(prev_map.keys())
    curr_ids = set(curr_map.keys())

    added = [curr_map[i] for i in curr_ids - prev_ids]
    removed = [prev_map[i] for i in prev_ids - curr_ids]

    updated = []
    for pid in prev_ids & curr_ids:
        if prev_map[pid].get("excerpt") != curr_map[pid].get("excerpt"):
            updated.append({
                "id": pid,
                "title": curr_map[pid]["title"],
                "url": curr_map[pid].get("url", ""),
                "before": prev_map[pid].get("excerpt", ""),
                "after": curr_map[pid].get("excerpt", ""),
            })

    if not added and not removed and not updated:
        return {"status": "checked"}

    return {
        "status": "updated",
        "added": added,
        "removed": removed,
        "updated": updated,
    }


def load_snapshot(file_path):
    """Load a JSON snapshot file."""
    path = Path(file_path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _hash_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
