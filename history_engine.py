#!/usr/bin/env python3
"""
History engine — read-only queries over the positions snapshot history.

Slack/env-independent (mirrors analysis_engine.py). Every daily snapshot
(`data/<company>/<YYYYMMDD>_<prefix>_positions.json`) stores the FULL set of
positions open that day, description body included — so a position that was
later removed still lives, verbatim, in the last snapshot it appeared in.
This module surfaces those "deleted" (no-longer-posted) positions and their
full record without re-crawling anything.

CLI-testable:
    .venv/bin/python history_engine.py <company> [start YYYYMMDD] [end YYYYMMDD]
"""

import sys

from analysis_engine import (
    COMPANIES,
    resolve_company,
    snapshots_in_range,
    list_snapshot_dates,
    _fmt_date,
)
from compare_utils import load_snapshot


def _full_range(company):
    dates = list_snapshot_dates(company["data_dir"], company["prefix"], "positions")
    if not dates:
        return None, None
    return dates[0], dates[-1]


def _load_history(company, start=None, end=None):
    """
    Load every positions snapshot in [start, end] (defaults to the company's full
    history). Returns (loaded, start, end) where loaded = [(date, list[dict]), ...]
    in ascending date order. loaded is [] when no snapshots exist.
    """
    a, b = _full_range(company)
    start = start or a
    end = end or b
    if start is None:
        return [], None, None
    snaps = snapshots_in_range(company["data_dir"], company["prefix"], "positions", start, end)
    loaded = [(d, load_snapshot(p) or []) for d, p in snaps]
    return loaded, start, end


def deleted_positions(company, start=None, end=None):
    """
    Positions that appeared at some point in [start, end] but are NOT present in
    the latest snapshot of that range — i.e. removed/closed and not currently open.

    Deduped by id (so a title shared by two distinct jobs stays distinct, and a
    job that reopened and is now live is excluded). Sorted by last_seen desc, then
    title asc. Each item: {id, title, location, first_seen, last_seen}.
    """
    loaded, _, _ = _load_history(company, start, end)
    if not loaded:
        return []

    meta = {}  # id -> aggregated metadata across its appearances
    for date, data in loaded:
        for p in data:
            pid = p.get("id")
            if pid is None:
                continue
            m = meta.get(pid)
            if m is None:
                meta[pid] = {
                    "id": pid,
                    "title": p.get("title", ""),
                    "location": p.get("location", ""),
                    "first_seen": date,
                    "last_seen": date,
                }
            else:
                m["last_seen"] = date
                # Track the most recent title/location it was posted under.
                m["title"] = p.get("title", m["title"])
                m["location"] = p.get("location", m["location"])

    latest_ids = {p.get("id") for p in loaded[-1][1]}
    deleted = [m for pid, m in meta.items() if pid not in latest_ids]

    # last_seen desc, title asc (stable sort: apply title first, then last_seen).
    deleted.sort(key=lambda m: m["title"])
    deleted.sort(key=lambda m: m["last_seen"], reverse=True)
    return deleted


def get_position_record(company, position_id, start=None, end=None):
    """
    Most-recent full snapshot record (description/compensation/url included) for a
    position id within [start, end]. Returns (record, last_seen_date) or (None, None).
    """
    loaded, _, _ = _load_history(company, start, end)
    for date, data in reversed(loaded):
        for p in data:
            if p.get("id") == position_id:
                return p, date
    return None, None


# ==========================================
# CLI (standalone verification — no Slack/env)
# ==========================================

def _main():
    if len(sys.argv) < 2:
        print("usage: history_engine.py <company> [start YYYYMMDD] [end YYYYMMDD]")
        print("companies:", ", ".join(COMPANIES))
        return
    key = resolve_company(sys.argv[1])
    if not key:
        print(f"unknown company: {sys.argv[1]}")
        return
    company = COMPANIES[key]
    start = sys.argv[2] if len(sys.argv) > 2 else None
    end = sys.argv[3] if len(sys.argv) > 3 else None

    items = deleted_positions(company, start, end)
    print(f"== {company['name']} — deleted (no-longer-posted) positions: {len(items)} ==")
    for i, m in enumerate(items):
        loc = f" · {m['location']}" if m["location"] else ""
        print(f"[{i:2}] {m['title']}{loc}"
              f"  (first {_fmt_date(m['first_seen'])} → last {_fmt_date(m['last_seen'])})")

    if items:
        rec, last_seen = get_position_record(company, items[0]["id"], start, end)
        print(f"\n-- full body of [0] {items[0]['title']} (last seen {_fmt_date(last_seen)}) --")
        print((rec or {}).get("description", "")[:800])


if __name__ == "__main__":
    _main()
