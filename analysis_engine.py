#!/usr/bin/env python3
"""
analysis_engine.py — On-demand competitive analysis engine.

Pure functions over the date-prefixed snapshots in data/<company>/.
No Slack / no env dependency: importable by slack_bot.py and runnable standalone:

    .venv/bin/python analysis_engine.py <company> [startYYYYMMDD] [endYYYYMMDD]

Because each dated file is a FULL snapshot (not a diff), we walk every snapshot
in the window pairwise to capture true open/close churn — including roles that
opened AND closed inside the window, which an endpoint-only diff would miss.
"""

import json
import re
import sys
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

from compare_utils import compare_positions, compare_blogs, load_snapshot

BASE_DIR = Path(__file__).resolve().parent

# Data-only company config. slack_bot keeps its own COMPANIES and passes those
# dicts into the engine functions; this map exists for the standalone CLI.
COMPANIES = {
    "physical_intelligence": {"name": "Physical Intelligence", "prefix": "pi", "data_dir": BASE_DIR / "data" / "physical_intelligence"},
    "skild_ai": {"name": "Skild AI", "prefix": "skild", "data_dir": BASE_DIR / "data" / "skild_ai"},
    "dyna": {"name": "DYNA", "prefix": "dyna", "data_dir": BASE_DIR / "data" / "dyna"},
    "generalist_ai": {"name": "Generalist AI", "prefix": "generalist", "data_dir": BASE_DIR / "data" / "generalist_ai"},
    "sunday": {"name": "Sunday Robotics", "prefix": "sunday", "data_dir": BASE_DIR / "data" / "sunday"},
    "genesis": {"name": "Genesis AI", "prefix": "genesis", "data_dir": BASE_DIR / "data" / "genesis"},
    "rhoda": {"name": "Rhoda AI", "prefix": "rhoda", "data_dir": BASE_DIR / "data" / "rhoda"},
}

# token -> canonical company key
ALIASES = {
    "pi": "physical_intelligence", "physical": "physical_intelligence",
    "physical_intelligence": "physical_intelligence", "physicalintelligence": "physical_intelligence",
    "skild": "skild_ai", "skild_ai": "skild_ai", "skildai": "skild_ai",
    "dyna": "dyna",
    "generalist": "generalist_ai", "generalist_ai": "generalist_ai", "generalistai": "generalist_ai",
    "sunday": "sunday", "sunday_robotics": "sunday", "sundayrobotics": "sunday",
    "genesis": "genesis", "genesis_ai": "genesis", "genesisai": "genesis",
    "rhoda": "rhoda", "rhoda_ai": "rhoda", "rhodaai": "rhoda",
}


def resolve_company(token):
    """Resolve a user token (key/prefix/alias/display name) to a company key, or None."""
    if not token:
        return None
    t = token.strip().lower().replace(" ", "_")
    if t in ALIASES:
        return ALIASES[t]
    t2 = t.replace("_", "")
    if t2 in ALIASES:
        return ALIASES[t2]
    # Prefix fallback: match the token as a PREFIX of an alias, and accept it
    # only when it unambiguously points to ONE company. This keeps 'rho'->rhoda
    # and 'skil'->skild_ai working while refusing ambiguous/garbage tokens —
    # e.g. 'gen' (genesis vs generalist) and 'ai' now return None instead of
    # silently mis-routing to the wrong company (was: bidirectional substring).
    if len(t2) >= 3:
        hits = {key for alias, key in ALIASES.items() if alias.replace("_", "").startswith(t2)}
        if len(hits) == 1:
            return next(iter(hits))
    return None


# ==========================================
# Classification (deterministic keyword scoring, no API cost)
# ==========================================

# Each (keyword, weight). A title is scored per category; highest score wins,
# ties broken by FUNCTION_PRIORITY order. This correctly routes e.g.
# "Staff Machine Learning Infrastructure Engineer" -> Software/Infra (infra 3 > ml 2)
# and "Robotics Research Engineer" -> Research/ML (research 3 > robot 1).
FUNCTION_KEYWORDS = {
    "Research/ML": [
        ("research", 3), ("scientist", 3), ("machine learning", 2), (" ml ", 2),
        ("deep learning", 3), ("learning", 1), ("computer vision", 3), ("perception", 2),
        ("foundation model", 3), ("reinforcement", 2), ("imitation", 2), ("manipulation", 2),
        ("post training", 3), ("post-training", 3), ("pretraining", 3), ("pre-training", 3),
        ("training", 1), ("ai engineer", 2),
    ],
    "Hardware/Robotics": [
        ("mechanical", 3), ("electrical", 3), ("mechatron", 3), ("firmware", 3), ("hardware", 3),
        ("robot build", 3), ("robot integration", 3), ("robot test", 3), ("robot prototype", 3),
        ("manufacturing", 2), ("industrial design", 3), ("motor", 2), ("actuator", 3),
        ("embedded", 2), ("technician", 2), ("robot", 1),
    ],
    "Software/Infra": [
        ("software", 3), ("infrastructure", 3), ("infra", 2), ("platform", 2), ("backend", 2),
        ("frontend", 2), ("full stack", 3), ("fullstack", 3), ("devops", 3), ("compiler", 3),
        ("inference", 2), ("developer", 2), ("cloud", 2), ("rendering", 2), ("simulation", 2),
        ("systems engineer", 2), ("designer", 1), ("ux", 1),
    ],
    "Data/Ops": [
        ("data collection", 3), ("annotat", 3), ("operator", 3), ("teleoperation", 3),
        ("teleop", 3), ("data operations", 3), ("data ops", 3), ("data strategist", 2),
        ("qa", 2), ("tester", 2), ("inventory", 2), ("logistics", 2), ("production support", 3),
        ("assembly", 2), ("operations", 1), ("data", 1),
    ],
    "Business/G&A": [
        ("chief of staff", 3), ("talent", 3), ("recruit", 3), ("marketing", 3), ("communications", 2),
        ("finance", 3), ("legal", 3), ("counsel", 3), ("office manager", 3), ("community", 2),
        ("creative", 2), ("product manager", 3), ("head of product", 3), ("partnerships", 2),
        ("success manager", 3), ("strategy", 1), ("people", 2), ("business operations", 2),
        ("biz ops", 3), ("executive assistant", 3), (" hr ", 2), ("account", 2), ("sales", 2),
    ],
}
FUNCTION_PRIORITY = ["Research/ML", "Software/Infra", "Hardware/Robotics", "Data/Ops", "Business/G&A"]


def classify_function(title):
    t = " " + re.sub(r"[&/:,\-]", " ", (title or "").lower()) + " "
    scores = {}
    for cat, kws in FUNCTION_KEYWORDS.items():
        scores[cat] = sum(w for kw, w in kws if kw in t)
    best = max(FUNCTION_PRIORITY, key=lambda c: (scores[c], -FUNCTION_PRIORITY.index(c)))
    return best if scores[best] > 0 else "Other"


def classify_seniority(title):
    t = (title or "").lower()
    if "intern" in t or "new grad" in t or "new-grad" in t:
        return "Intern/New-grad"
    if "chief of staff" in t:
        return "Lead/Manager"
    if "technical staff" in t or "of staff" in t:  # IC-convention title (e.g. Member of Technical Staff), not a level
        return "Unspecified"
    if "principal" in t or "distinguished" in t or re.search(r"\bstaff\b", t):
        return "Staff/Principal"
    if any(k in t for k in ["lead", "manager", "director", "head of", "vp ", "vice president", "chief"]):
        return "Lead/Manager"
    if "senior" in t or "sr." in t or re.search(r"\bsr\b", t):
        return "Senior"
    if re.search(r"\b(ii|iii|iv)\b", t):
        return "Mid"
    return "Unspecified"


THEME_KEYWORDS = {
    "Foundation model": ["foundation model"],
    "VLA / multimodal": ["vla", "vision-language", "vision language", "multimodal"],
    "Manipulation / dexterity": ["manipulation", "grasp", "dexter"],
    "Locomotion / humanoid": ["locomotion", "legged", "humanoid", "walking"],
    "Sim / sim2real": ["sim2real", "sim-to-real", "simulation", "simulator"],
    "RL / imitation": ["reinforcement learning", "imitation learning", "policy learning"],
    "Teleop / data": ["teleoperation", "teleop", "data collection", "dataset"],
    "Perception / vision": ["perception", "computer vision"],
    "Deployment / product": ["deployment", "production", "real-world", "real world", "commercial"],
    "Safety / robustness": ["safety", "robustness", "reliab"],
}


def extract_themes(posts):
    text = " ".join(
        (p.get("title", "") + " " + p.get("excerpt", "") + " " + p.get("content", "")) for p in posts
    ).lower()
    counts = {}
    for theme, kws in THEME_KEYWORDS.items():
        c = sum(text.count(k) for k in kws)
        if c:
            counts[theme] = c
    return sorted(counts.items(), key=lambda x: -x[1])


# ==========================================
# Snapshot / timeline helpers
# ==========================================

def list_snapshot_dates(data_dir, prefix, file_type):
    data_dir = Path(data_dir)
    dates = set()
    for f in data_dir.glob(f"[0-9]*_{prefix}_{file_type}.json"):
        d = f.name.split("_")[0]
        if len(d) == 8 and d.isdigit():
            dates.add(d)
    return sorted(dates)


def snapshots_in_range(data_dir, prefix, file_type, start, end):
    data_dir = Path(data_dir)
    out = []
    for d in list_snapshot_dates(data_dir, prefix, file_type):
        if start <= d <= end:
            out.append((d, data_dir / f"{d}_{prefix}_{file_type}.json"))
    return out


def available_range(company):
    """(first, last) snapshot date across positions+blog, or (None, None)."""
    dates = []
    for ft in ("positions", "blog"):
        dates += list_snapshot_dates(company["data_dir"], company["prefix"], ft)
    if not dates:
        return None, None
    dates.sort()
    return dates[0], dates[-1]


def _to_dt(yyyymmdd):
    return datetime.strptime(yyyymmdd, "%Y%m%d")


def _days_between(a, b):
    return (_to_dt(b) - _to_dt(a)).days


def _norm_date(s):
    s = str(s or "").strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return "".join(m.groups())
    if len(s) == 8 and s.isdigit():
        return s
    return None


# ==========================================
# Event extraction (the snapshot walk)
# ==========================================

def build_position_events(company, start, end):
    """Walk every positions snapshot in [start, end] pairwise to extract events."""
    snaps = snapshots_in_range(company["data_dir"], company["prefix"], "positions", start, end)
    result = {
        "snapshots": [d for d, _ in snaps],
        "first_date": snaps[0][0] if snaps else None,
        "last_date": snaps[-1][0] if snaps else None,
        "headcount_series": [],
        "opens": [], "closes": [], "modifies": [], "reopens": [],
        "start_state": [], "end_state": [],
    }
    if not snaps:
        return result

    loaded = []
    for d, p in snaps:
        data = load_snapshot(p) or []
        loaded.append((d, data))
        # Count DISTINCT ids so headcount agrees with the id-deduped event walk
        # (velocity/opens/closes). Raw len(data) would double-count snapshots
        # with duplicate ids (e.g. a slug collision) and make net headcount
        # contradict net velocity in the same card.
        result["headcount_series"].append((d, len({p.get("id") for p in data})))
    result["start_state"] = loaded[0][1]
    result["end_state"] = loaded[-1][1]

    first_open = {}   # id -> first date it appeared (within window)
    last_closed = {}  # id -> date it was last removed
    for i in range(len(loaded) - 1):
        _, prev = loaded[i]
        d_curr, curr = loaded[i + 1]
        diff = compare_positions(prev, curr)
        if diff.get("status") != "updated":
            continue
        for p in diff.get("added", []):
            pid = p["id"]
            if pid in last_closed:
                result["reopens"].append({"id": pid, "title": p.get("title", ""),
                                          "closed": last_closed.pop(pid), "reopened": d_curr})
            result["opens"].append({
                "id": pid, "title": p.get("title", ""), "location": p.get("location", ""),
                "date": d_curr, "function": classify_function(p.get("title", "")),
                "seniority": classify_seniority(p.get("title", "")),
            })
            first_open.setdefault(pid, d_curr)
        for p in diff.get("removed", []):
            pid = p["id"]
            opened = first_open.get(pid)
            result["closes"].append({
                "id": pid, "title": p.get("title", ""), "date": d_curr,
                "days_open": _days_between(opened, d_curr) if opened else None,
                "function": classify_function(p.get("title", "")),
            })
            last_closed[pid] = d_curr
        for u in diff.get("updated", []):
            result["modifies"].append({"id": u["id"], "title": u.get("title", ""), "date": d_curr})
    return result


def build_blog_metrics(company, start, end):
    """Posts published in window (by post date) + edits detected via snapshot walk."""
    snaps = snapshots_in_range(company["data_dir"], company["prefix"], "blog", start, end)
    out = {"snapshots": [d for d, _ in snaps], "published": [], "edits": [],
           "has_full_content": False, "themes": [], "total_posts": 0}
    if not snaps:
        return out

    end_data = load_snapshot(snaps[-1][1]) or []
    out["total_posts"] = len(end_data)
    out["has_full_content"] = any("content" in p for p in end_data)

    for p in end_data:
        pd = _norm_date(p.get("date", ""))
        if pd and start <= pd <= end:
            out["published"].append({
                "title": p.get("title", ""), "date": p.get("date", ""),
                "type": p.get("type") or p.get("category", ""), "url": p.get("url", ""),
            })
    out["published"].sort(key=lambda x: x.get("date", ""))

    loaded = [(d, load_snapshot(pp) or []) for d, pp in snaps]
    for i in range(len(loaded) - 1):
        diff = compare_blogs(loaded[i][1], loaded[i + 1][1])
        if diff.get("status") == "updated":
            for u in diff.get("updated", []):
                out["edits"].append({"title": u.get("title", ""), "date": loaded[i + 1][0]})

    theme_src = [p for p in end_data if _norm_date(p.get("date", "")) and start <= _norm_date(p.get("date", "")) <= end]
    out["themes"] = extract_themes(theme_src or end_data)
    return out


# ==========================================
# Aggregation
# ==========================================

def _mix(state, fn):
    return Counter(fn(p.get("title", "")) for p in state)


def compute_metrics(company, start, end, events, blog):
    series = events["headcount_series"]
    n_snaps = len(series)
    single = n_snaps <= 1

    span_weeks = None
    if events["first_date"] and events["last_date"] and events["first_date"] != events["last_date"]:
        span_weeks = max(_days_between(events["first_date"], events["last_date"]) / 7.0, 0.001)

    func_end = _mix(events["end_state"], classify_function)
    func_start = _mix(events["start_state"], classify_function)
    sen_end = _mix(events["end_state"], classify_seniority)

    locs_end = [p.get("location", "").strip() for p in events["end_state"] if p.get("location", "").strip()]
    locs_start = {p.get("location", "").strip() for p in events["start_state"] if p.get("location", "").strip()}
    loc_counter = Counter(locs_end)

    comp = [(p.get("title", ""), p.get("compensation", "").strip())
            for p in events["end_state"] if p.get("compensation", "").strip()]
    equity_count = sum(1 for _, c in comp if "equity" in c.lower())

    closed_days = [c["days_open"] for c in events["closes"] if c.get("days_open") is not None]
    opened_dates = {o["id"]: o["date"] for o in events["opens"]}
    aging = sorted(
        ((p.get("title", ""), _days_between(opened_dates[p["id"]], events["last_date"]))
         for p in events["end_state"] if p["id"] in opened_dates and events["last_date"]),
        key=lambda x: -x[1],
    )

    n_opens, n_closes = len(events["opens"]), len(events["closes"])
    return {
        "company": company["name"],
        "period": {
            "requested": (start, end), "actual_start": events["first_date"], "actual_end": events["last_date"],
            "n_snapshots": n_snaps, "span_weeks": span_weeks, "single": single,
            "clamped": (events["first_date"] != start or events["last_date"] != end) if events["first_date"] else False,
        },
        "headcount": {
            "start": series[0][1] if series else 0, "end": series[-1][1] if series else 0,
            "net": (series[-1][1] - series[0][1]) if series else 0,
            "peak": max((c for _, c in series), default=0),
            "min": min((c for _, c in series), default=0),
        },
        "velocity": {
            "opens": n_opens, "closes": n_closes, "net": n_opens - n_closes,
            "modifies": len(events["modifies"]), "reopens": len(events["reopens"]),
            "opens_per_week": (n_opens / span_weeks) if span_weeks else None,
            "closes_per_week": (n_closes / span_weeks) if span_weeks else None,
        },
        "function_mix": {
            "end": dict(func_end),
            "delta": {k: func_end.get(k, 0) - func_start.get(k, 0) for k in set(func_end) | set(func_start)},
        },
        "seniority_mix": dict(sen_end),
        "geo": {"has_geo": bool(locs_end), "distinct": len(set(locs_end)),
                "top": loc_counter.most_common(6), "new": sorted(set(loc_counter) - locs_start)},
        "comp": {"items": comp, "equity_count": equity_count},
        "longevity": {
            "closed_avg_days": (statistics.mean(closed_days) if closed_days else None),
            "closed_median_days": (statistics.median(closed_days) if closed_days else None),
            "n_closed_with_days": len(closed_days),
            "oldest_open": aging[:3],
        },
        "events": events,
        "blog": blog,
    }


def analyze(company, start=None, end=None):
    """Top-level: returns (metrics, error). error is a dict if no data in window."""
    first, last = available_range(company)
    if not first:
        return None, {"reason": "no_data"}
    start = start or first
    end = end or last
    events = build_position_events(company, start, end)
    blog = build_blog_metrics(company, start, end)
    if not events["snapshots"] and not blog["snapshots"]:
        return None, {"reason": "empty_range", "available": (first, last)}
    return compute_metrics(company, start, end, events, blog), None


# ==========================================
# AI prompt (shared by CLI test + slack_bot)
# ==========================================

def _fmt_date(yyyymmdd):
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}" if yyyymmdd and len(yyyymmdd) == 8 else (yyyymmdd or "?")


def _mix_line(counter_dict):
    return ", ".join(f"{k} {v}" for k, v in sorted(counter_dict.items(), key=lambda x: -x[1]) if v)


def build_ai_prompt(m):
    p, v, hc = m["period"], m["velocity"], m["headcount"]
    ev, blog = m["events"], m["blog"]
    lines = [f"다음은 {m['company']}의 경쟁사 모니터링 분석 데이터입니다 "
             f"(실제 분석 구간 {_fmt_date(p['actual_start'])} ~ {_fmt_date(p['actual_end'])}, 스냅샷 {p['n_snapshots']}개)."]

    if p["single"]:
        lines.append("\n[주의] 스냅샷이 1개뿐이라 추세/속도는 없고 현재 현황만 있습니다.")
        lines.append(f"\n현재 포지션 {hc['end']}개")
    else:
        lines.append(f"\n[채용 규모] {hc['start']} → {hc['end']}개 (순증감 {hc['net']:+d}, 기간 중 최대 {hc['peak']})")
        opw = f"{v['opens_per_week']:.1f}" if v["opens_per_week"] is not None else "?"
        cpw = f"{v['closes_per_week']:.1f}" if v["closes_per_week"] is not None else "?"
        lines.append(f"[채용 속도] 신규오픈 {v['opens']} / 마감 {v['closes']} (순 {v['net']:+d}) · "
                     f"주당 오픈 {opw} 마감 {cpw} · JD재작성 {v['modifies']} · 재오픈 {v['reopens']}")

    lines.append(f"[직무 믹스 - 현재] {_mix_line(m['function_mix']['end']) or '없음'}")
    delta = {k: d for k, d in m["function_mix"]["delta"].items() if d}
    if delta and not p["single"]:
        lines.append(f"[직무 믹스 변화] " + ", ".join(f"{k} {d:+d}" for k, d in sorted(delta.items(), key=lambda x: -abs(x[1]))))
    lines.append(f"[시니어리티] {_mix_line(m['seniority_mix']) or '없음'}")

    if m["geo"]["has_geo"]:
        top = ", ".join(f"{loc}({n})" for loc, n in m["geo"]["top"])
        lines.append(f"[지역] 거점 {m['geo']['distinct']}곳 · 상위: {top}" +
                     (f" · 신규: {', '.join(m['geo']['new'])}" if m["geo"]["new"] else ""))

    if m["comp"]["items"]:
        lines.append(f"[보상 공개 {len(m['comp']['items'])}건, equity {m['comp']['equity_count']}건]")
        for title, c in m["comp"]["items"][:8]:
            lines.append(f"  - {title}: {c}")

    if ev["opens"]:
        lines.append(f"\n[신규 오픈 포지션 {len(ev['opens'])}건 중 일부]")
        for o in ev["opens"][:15]:
            lines.append(f"  + ({_fmt_date(o['date'])}) {o['title']} [{o['function']}/{o['seniority']}]")
    if ev["closes"]:
        lines.append(f"\n[마감된 포지션 {len(ev['closes'])}건 중 일부]")
        for c in ev["closes"][:10]:
            d = f", {c['days_open']}일 열림" if c.get("days_open") is not None else ""
            lines.append(f"  - ({_fmt_date(c['date'])}) {c['title']}{d}")
    if ev["modifies"]:
        lines.append(f"\n[JD 재작성(설명 변경) {len(ev['modifies'])}건 중 일부]")
        for u in ev["modifies"][:8]:
            lines.append(f"  ~ ({_fmt_date(u['date'])}) {u['title']}")
    if ev["reopens"]:
        lines.append(f"\n[재오픈 {len(ev['reopens'])}건] " + ", ".join(r["title"] for r in ev["reopens"][:6]))

    if blog["published"]:
        lines.append(f"\n[블로그/리서치 발행 {len(blog['published'])}건]")
        for b in blog["published"][:10]:
            lines.append(f"  • [{b['date']}] {b['title']} ({b['type']})")
    if blog["themes"]:
        lines.append("[블로그 테마] " + ", ".join(f"{t}({n})" for t, n in blog["themes"][:6]))
    if blog["edits"]:
        lines.append(f"[블로그 수정 감지 {len(blog['edits'])}건]")

    lines.append("""
=== 분석 요청 ===
위 데이터를 바탕으로 이 회사의 채용/리서치 전략을 해석해주세요.

*형식 규칙:*
- *Slack mrkdwn 형식 사용* (Bold는 *텍스트* — 별표 1개). ** 절대 금지.
- 간결한 불렛 중심, 각 불렛 아래 한 줄 근거(수치 인용).

*분석 항목:*
1. 🔍 핵심 변화 (가장 의미있는 채용/리서치 시그널)
2. 💡 전략 해석 (회사의 현재 단계와 방향성 — 직무/시니어리티/지역 믹스 근거)
3. 🔗 채용 ↔ 리서치 정합성 (블로그에서 말한 방향과 실제 채용이 일치하는가)
4. ⚠️ 특이사항 (급변, JD 재작성, 재오픈, 오래 열린 공고 등)

수치와 근거 중심으로 간결하게. *별표는 1개만* 사용하세요.""")
    return "\n".join(lines)


# ==========================================
# Slack mrkdwn chunking (3000-char per-block limit)
# ==========================================

def chunk_mrkdwn(text, limit=2900):
    if len(text) <= limit:
        return [text]
    chunks, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if cur and len(cur) + len(line) + 1 > limit:
            chunks.append(cur)
            cur = line
        else:
            cur = line if not cur else cur + "\n" + line
    if cur:
        chunks.append(cur)
    return chunks


# ==========================================
# CLI test harness (no Slack)
# ==========================================

def render_card_text(m):
    p, v, hc = m["period"], m["velocity"], m["headcount"]
    out = [f"📊 {m['company']} — 경쟁사 분석",
           f"   실제 구간 {_fmt_date(p['actual_start'])} ~ {_fmt_date(p['actual_end'])} · 스냅샷 {p['n_snapshots']}개"
           + ("  [요청 범위와 다름]" if p["clamped"] else "")]
    if p["single"]:
        out.append("   ⚠️ 스냅샷 1개 — 현황 스냅만 (추세/속도 불가)")
        out.append(f"👥 현재 포지션 {hc['end']}개")
    else:
        out.append(f"👥 채용 규모: {hc['start']} → {hc['end']} (순 {hc['net']:+d}, 최대 {hc['peak']})")
        opw = f"{v['opens_per_week']:.1f}" if v["opens_per_week"] is not None else "?"
        out.append(f"⚡ 속도: +{v['opens']} / -{v['closes']} (순 {v['net']:+d}) · 주당오픈 {opw} · "
                   f"JD재작성 {v['modifies']} · 재오픈 {v['reopens']}")
    out.append(f"🧩 직무: {_mix_line(m['function_mix']['end'])}")
    out.append(f"🎚️ 시니어리티: {_mix_line(m['seniority_mix'])}")
    if m["geo"]["has_geo"]:
        out.append(f"🌍 지역 {m['geo']['distinct']}곳: " + ", ".join(f"{l}({n})" for l, n in m["geo"]["top"]) +
                   (f" · 신규: {', '.join(m['geo']['new'])}" if m["geo"]["new"] else ""))
    if m["comp"]["items"]:
        out.append(f"💰 보상 {len(m['comp']['items'])}건 공개 (equity {m['comp']['equity_count']})")
    lg = m["longevity"]
    if lg["closed_median_days"] is not None:
        out.append(f"⏳ 공고수명(마감기준) 중앙값 {lg['closed_median_days']:.0f}일 (n={lg['n_closed_with_days']})")
    b = m["blog"]
    out.append(f"📝 블로그: 기간발행 {len(b['published'])} · 수정 {len(b['edits'])} · 본문보유 {b['has_full_content']}")
    if b["themes"]:
        out.append("   테마: " + ", ".join(f"{t}({n})" for t, n in b["themes"][:6]))
    return "\n".join(out)


def _main():
    if len(sys.argv) < 2:
        print("usage: python analysis_engine.py <company> [startYYYYMMDD] [endYYYYMMDD]")
        print("companies:", ", ".join(COMPANIES))
        sys.exit(1)
    key = resolve_company(sys.argv[1])
    if not key:
        print(f"unknown company: {sys.argv[1]}\ncompanies: {', '.join(COMPANIES)}")
        sys.exit(1)
    start = sys.argv[2] if len(sys.argv) > 2 else None
    end = sys.argv[3] if len(sys.argv) > 3 else None
    metrics, err = analyze(COMPANIES[key], start, end)
    if err:
        print("no analyzable data:", err)
        sys.exit(1)
    print("=" * 70)
    print(render_card_text(metrics))
    print("=" * 70)
    print("\n----- AI PROMPT (preview) -----\n")
    print(build_ai_prompt(metrics))


if __name__ == "__main__":
    _main()
