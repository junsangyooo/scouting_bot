import json
import hashlib
from pathlib import Path

DATA_PATH = Path("data/physical_intelligence/positions.json")


def position_compare(curr_positions):
    """
    Compare current positions with previous snapshot.

    Returns:
    {
        status: "initialized" | "updated",
        added:   list[dict],
        removed: list[dict],
        updated: list[dict],  # JD changed
    }
    """

    # JD hash 추가 (변경 감지용)
    for pos in curr_positions:
        pos["description_hash"] = _hash_text(pos.get("description", ""))

    # 1️⃣ 최초 실행
    if not DATA_PATH.exists():
        _save(curr_positions)
        return {
            "status": "initialized",
            "added": [],
            "removed": [],
            "updated": []
        }

    # 2️⃣ 이전 데이터 로드
    prev_positions = json.loads(DATA_PATH.read_text(encoding="utf-8"))

    prev_map = {p["id"]: p for p in prev_positions}
    curr_map = {p["id"]: p for p in curr_positions}

    prev_ids = set(prev_map.keys())
    curr_ids = set(curr_map.keys())

    # 3️⃣ 신규 / 삭제
    added_ids = curr_ids - prev_ids
    removed_ids = prev_ids - curr_ids

    added = [curr_map[i] for i in added_ids]
    removed = [prev_map[i] for i in removed_ids]

    # 4️⃣ JD 변경 감지
    updated = []
    common_ids = prev_ids & curr_ids

    for pid in common_ids:
        if prev_map[pid].get("description_hash") != curr_map[pid].get("description_hash"):
            updated.append({
                "id": pid,
                "title": curr_map[pid]["title"],
                "before": prev_map[pid].get("description", ""),
                "after": curr_map[pid].get("description", "")
            })

    # 5️⃣ 현재 상태 저장
    _save(curr_positions)

    return {
        "status": "updated",
        "added": added,
        "removed": removed,
        "updated": updated
    }


# ---------- helpers ----------

def _save(positions):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(
        json.dumps(positions, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def _hash_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
