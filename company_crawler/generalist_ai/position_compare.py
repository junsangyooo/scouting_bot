import json
import hashlib
from pathlib import Path

DATA_PATH = Path("data/generalist_ai/generalist_positions.json")


def position_compare(curr_positions):
    # JD hash 추가
    for pos in curr_positions:
        pos["description_hash"] = _hash_text(pos.get("description", ""))

    # 최초 실행
    if not DATA_PATH.exists():
        _save(curr_positions)
        return {
            "status": "initialized",
            "added": [],
            "removed": [],
            "updated": [],
        }

    # 이전 데이터 로드
    prev_positions = json.loads(DATA_PATH.read_text(encoding="utf-8"))

    # Guard: a completely empty crawl almost always means the crawler broke
    # (selector/site change, network) — not that every posting truly vanished.
    # Never overwrite good data or fire a false "all removed" report on it.
    if not curr_positions and prev_positions:
        print(f"[WARN] Empty crawl but {len(prev_positions)} previous positions exist — "
              "treating as crawl failure; keeping previous data.")
        return {"status": "checked"}


    prev_map = {p["id"]: p for p in prev_positions}
    curr_map = {p["id"]: p for p in curr_positions}

    prev_ids = set(prev_map.keys())
    curr_ids = set(curr_map.keys())

    added = [curr_map[i] for i in curr_ids - prev_ids]
    removed = [prev_map[i] for i in prev_ids - curr_ids]

    # JD 변경 감지
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

    _save(curr_positions)
    return {
        "status": "updated",
        "added": added,
        "removed": removed,
        "updated": updated,
    }


def _save(positions):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(
        json.dumps(positions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _hash_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
