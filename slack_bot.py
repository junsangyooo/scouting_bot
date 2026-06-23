#!/usr/bin/env python3
"""
Scouting Bot — Slack Bot (Socket Mode)
Handles /analyze slash command and can send daily reports.
"""

import json
import os
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from claude_cli import run_claude

load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("scouting_bot")

# ==========================================
# App init
# ==========================================

app = App(
    token=os.getenv("SLACK_BOT_TOKEN"),
    signing_secret=os.getenv("SLACK_SIGNING_SECRET"),
)

CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID", "C0AR5NXH160")

# ==========================================
# Data config
# ==========================================

BASE_DIR = Path(__file__).resolve().parent

COMPANIES = {
    "physical_intelligence": {
        "name": "Physical Intelligence",
        "prefix": "pi",
        "data_dir": BASE_DIR / "data" / "physical_intelligence",
        "files": ["positions", "blog"],
        "career_url": "https://www.pi.website/join-us",
        "blog_url": "https://www.pi.website/blog",
    },
    "skild_ai": {
        "name": "Skild AI",
        "prefix": "skild",
        "data_dir": BASE_DIR / "data" / "skild_ai",
        "files": ["positions", "blog"],
        "career_url": "https://www.skild.ai/career",
        "blog_url": "https://www.skild.ai/blogs",
    },
    "dyna": {
        "name": "DYNA",
        "prefix": "dyna",
        "data_dir": BASE_DIR / "data" / "dyna",
        "files": ["positions", "blog"],
        "career_url": "https://jobs.ashbyhq.com/dyna-robotics",
        "blog_url": "https://www.dyna.co/research",
    },
    "generalist_ai": {
        "name": "Generalist AI",
        "prefix": "generalist",
        "data_dir": BASE_DIR / "data" / "generalist_ai",
        "files": ["positions", "blog"],
        "career_url": "https://generalistai.com/careers",
        "blog_url": "https://generalistai.com/blog",
    },
    "sunday": {
        "name": "Sunday Robotics",
        "prefix": "sunday",
        "data_dir": BASE_DIR / "data" / "sunday",
        "files": ["positions", "blog"],
        "career_url": "https://jobs.ashbyhq.com/sunday",
        "blog_url": "https://www.sunday.ai/journal",
    },
    "genesis": {
        "name": "Genesis AI",
        "prefix": "genesis",
        "data_dir": BASE_DIR / "data" / "genesis",
        "files": ["positions", "blog"],
        "career_url": "https://www.genesis.ai/careers",
        "blog_url": "https://www.genesis.ai/blog",
    },
    "rhoda": {
        "name": "Rhoda AI",
        "prefix": "rhoda",
        "data_dir": BASE_DIR / "data" / "rhoda",
        "files": ["positions", "blog"],
        "career_url": "https://www.rhoda.ai/careers",
        "blog_url": "https://www.rhoda.ai/news",
    },
}

# ==========================================
# Snapshot utilities
# ==========================================

from compare_utils import compare_positions, compare_blogs, load_snapshot
from analysis_engine import (
    resolve_company,
    analyze,
    build_ai_prompt,
    chunk_mrkdwn,
    _fmt_date,
    _mix_line,
)
from history_engine import deleted_positions, get_position_record


def find_snapshot(data_dir, prefix, file_type, date_str):
    """Find a snapshot file for a given date. e.g. 20260203_pi_positions.json"""
    path = data_dir / f"{date_str}_{prefix}_{file_type}.json"
    if path.exists():
        return path
    return None


def get_available_dates(data_dir, prefix):
    """Get all available snapshot dates for a company."""
    dates = set()
    for f in data_dir.glob(f"[0-9]*_{prefix}_*.json"):
        date_part = f.name.split("_")[0]
        if len(date_part) == 8 and date_part.isdigit():
            dates.add(date_part)
    return sorted(dates)


def compare_snapshots(start_date, end_date):
    """
    Compare snapshots between two dates for all companies.
    Returns structured diff data for Claude analysis.
    """
    results = {}

    for key, company in COMPANIES.items():
        prefix = company["prefix"]
        data_dir = company["data_dir"]
        company_result = {"name": company["name"]}

        for file_type in company["files"]:
            start_file = find_snapshot(data_dir, prefix, file_type, start_date)
            end_file = find_snapshot(data_dir, prefix, file_type, end_date)

            if not start_file or not end_file:
                company_result[file_type] = {
                    "status": "missing",
                    "message": f"Snapshot missing: start={start_file is not None}, end={end_file is not None}",
                }
                continue

            prev_data = load_snapshot(start_file)
            curr_data = load_snapshot(end_file)

            if prev_data is None or curr_data is None:
                company_result[file_type] = {"status": "error", "message": "Failed to load snapshot"}
                continue

            if file_type == "positions":
                company_result[file_type] = compare_positions(prev_data, curr_data)
            elif file_type == "blog":
                company_result[file_type] = compare_blogs(prev_data, curr_data)

        results[key] = company_result

    return results


def build_analysis_prompt(start_date, end_date, results):
    """Build a Claude analysis prompt from comparison results."""
    formatted_start = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
    formatted_end = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

    prompt = f"""다음은 {formatted_start} ~ {formatted_end} 기간 동안 {len(results)}개 로보틱스/AI 회사의 변화 데이터입니다.

"""
    for key, result in results.items():
        company_name = result["name"]
        prompt += f"\n{'='*60}\n{company_name}\n{'='*60}\n"

        for file_type in ["positions", "blog"]:
            data = result.get(file_type)
            if not data:
                continue

            if data.get("status") == "missing":
                prompt += f"\n[{file_type}] 데이터 없음\n"
                continue

            if data.get("status") == "checked":
                prompt += f"\n[{file_type}] 변경 없음\n"
                continue

            prompt += f"\n[{file_type}] 변경 감지\n"

            added = data.get("added", [])
            removed = data.get("removed", [])
            updated = data.get("updated", [])

            if added:
                prompt += f"\n신규 추가 ({len(added)}건):\n"
                prompt += json.dumps(added, ensure_ascii=False, indent=2) + "\n"
            if removed:
                prompt += f"\n삭제됨 ({len(removed)}건):\n"
                prompt += json.dumps(removed, ensure_ascii=False, indent=2) + "\n"
            if updated:
                prompt += f"\n변경됨 ({len(updated)}건):\n"
                prompt += json.dumps(updated, ensure_ascii=False, indent=2) + "\n"

    prompt += f"""

=== 분석 요청 ===
위 데이터를 바탕으로 {formatted_start} ~ {formatted_end} 기간의 변화를 분석해주세요.

*형식 규칙:*
- *Slack mrkdwn 형식 사용* (중요!)
- Bold는 *텍스트* (별표 1개)
- ** 절대 사용하지 마세요
- 최대한 간결하고 핵심적인 불렛 포인트만
- 회사별로 섹션을 나눠주세요

*분석 항목:*
1. 📋 기간 요약 (각 회사별 포지션/블로그 수 변화)
2. 🔍 주요 변화 (추가/삭제된 포지션, 새 블로그)
3. 💡 핵심 인사이트 (채용 전략 변화, 조직 방향성 등)
4. ⚠️ 특이사항 (Unusual한 패턴, 급격한 변화 등)

JD(Job Description) 변경이 있는 경우, 변경 내용의 핵심을 요약해주세요.
간결하게 작성해주세요. 핵심만! *별표는 1개만* 사용하세요."""

    return prompt


def run_claude_analysis(prompt):
    """Run Claude CLI to analyze the data (retry + backoff via claude_cli).

    Returns the analysis text, or None after retries are exhausted. The callers
    already degrade gracefully on None (post a "AI 분석 생성에 실패했습니다" reply)."""
    return run_claude(prompt, label="slack", log=logger.warning)


# ==========================================
# /analyze command
# ==========================================

@app.command("/analyze")
def handle_analyze(ack, respond, command):
    ack()

    text = command.get("text", "").strip()
    args = text.split()

    # Parse arguments
    if len(args) == 0:
        respond("사용법: `/analyze [시작날짜] [종료날짜]`\n예시: `/analyze 20260203 20260406`\n종료날짜 생략 시 오늘까지 분석합니다.")
        return

    start_date = args[0]
    end_date = args[1] if len(args) >= 2 else datetime.now().strftime("%Y%m%d")

    # Validate date format
    for date_str, label in [(start_date, "시작날짜"), (end_date, "종료날짜")]:
        if len(date_str) != 8 or not date_str.isdigit():
            respond(f"❌ {label} 형식이 잘못되었습니다: `{date_str}`\n`YYYYMMDD` 형식으로 입력해주세요. (예: 20260203)")
            return

    if start_date > end_date:
        respond("❌ 시작날짜가 종료날짜보다 뒤입니다.")
        return

    formatted_start = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
    formatted_end = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

    respond(f"🔍 *{formatted_start} ~ {formatted_end}* 기간 분석 중... 잠시만 기다려주세요.")

    # Compare snapshots
    results = compare_snapshots(start_date, end_date)

    # Check if any data exists
    all_missing = all(
        all(
            result.get(ft, {}).get("status") == "missing"
            for ft in COMPANIES[key]["files"]
        )
        for key, result in results.items()
    )

    if all_missing:
        available = {}
        for key, company in COMPANIES.items():
            dates = get_available_dates(company["data_dir"], company["prefix"])
            if dates:
                available[company["name"]] = f"{dates[0]} ~ {dates[-1]}"

        msg = f"❌ *{formatted_start}* 또는 *{formatted_end}* 날짜의 스냅샷을 찾을 수 없습니다.\n\n"
        msg += "*사용 가능한 날짜 범위:*\n"
        for name, range_str in available.items():
            msg += f"• {name}: `{range_str}`\n"

        app.client.chat_postMessage(channel=command["channel_id"], text=msg)
        return

    # Post a compact root message; the summary + AI analysis go into its thread
    # so the channel timeline stays one line per /analyze.
    root_resp = app.client.chat_postMessage(
        channel=command["channel_id"],
        text=f"📊 *Company Change Analysis* — {formatted_start} → {formatted_end}\n_결과·AI 분석은 이 스레드에 ⬇️_",
        unfurl_links=False,
        unfurl_media=False,
    )
    thread_ts = root_resp["ts"]

    # Summary (Block Kit) as the first thread reply.
    summary_blocks = build_summary_blocks(start_date, end_date, results)
    app.client.chat_postMessage(
        channel=command["channel_id"],
        thread_ts=thread_ts,
        text=f"📊 {formatted_start} ~ {formatted_end} 분석 결과",
        blocks=summary_blocks,
        unfurl_links=False,   # suppress automatic link-preview cards
        unfurl_media=False,
    )

    # Run Claude analysis — posted as further thread replies under the root.
    prompt = build_analysis_prompt(start_date, end_date, results)
    analysis = run_claude_analysis(prompt)

    if analysis:
        header = f"🤖 *AI 분석 ({formatted_start} ~ {formatted_end})*\n\n"
        for i, chunk in enumerate(chunk_mrkdwn(analysis)):
            app.client.chat_postMessage(
                channel=command["channel_id"],
                thread_ts=thread_ts,
                text=(header + chunk) if i == 0 else chunk,
                unfurl_links=False,
                unfurl_media=False,
            )
    else:
        app.client.chat_postMessage(
            channel=command["channel_id"],
            thread_ts=thread_ts,
            text="⚠️ AI 분석 생성에 실패했습니다.",
        )


def _linked_label(text, url):
    """Slack mrkdwn bold label, linked to `url` when available."""
    return f"*<{url}|{text}>:*" if url else f"*{text}:*"


def build_summary_blocks(start_date, end_date, results):
    """Build Slack Block Kit blocks for the comparison summary."""
    formatted_start = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
    formatted_end = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📊 Company Change Analysis",
                "emoji": True,
            },
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"*Period:* {formatted_start} → {formatted_end}"}
            ],
        },
        {"type": "divider"},
    ]

    for key, result in results.items():
        company_name = result["name"]
        company_cfg = COMPANIES.get(key, {})
        text = f"*{company_name}*\n"

        for file_type in ["positions", "blog"]:
            data = result.get(file_type)
            if not data:
                continue

            status = data.get("status", "")
            label = {"positions": "Career", "blog": "Blog"}.get(file_type, file_type)
            url = company_cfg.get("career_url" if file_type == "positions" else "blog_url")
            label_md = _linked_label(label, url)

            if status == "missing":
                text += f"• {label_md} ⚠️ 데이터 없음\n"
            elif status == "checked":
                text += f"• {label_md} ✅ 변경 없음\n"
            elif status == "updated":
                added = data.get("added", [])
                removed = data.get("removed", [])
                updated = data.get("updated", [])

                parts = []
                if added:
                    parts.append(f"+{len(added)} 추가")
                if removed:
                    parts.append(f"-{len(removed)} 삭제")
                if updated:
                    parts.append(f"~{len(updated)} 변경")

                text += f"• {label_md} {', '.join(parts)}\n"

                if added:
                    for item in added:
                        name = item if isinstance(item, str) else item.get("title", "?")
                        text += f"  ＋ {name}\n"
                if removed:
                    for item in removed:
                        name = item if isinstance(item, str) else item.get("title", "?")
                        text += f"  － {name}\n"
                if updated:
                    for item in updated:
                        title = item if isinstance(item, str) else item.get("title", "?")
                        text += f"  ✏️ {title}\n"

        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
        blocks.append({"type": "divider"})

    return blocks


# ==========================================
# /company_analyze command
# ==========================================

@app.command("/company_analyze")
def handle_company_analyze(ack, respond, command):
    ack()

    text = command.get("text", "").strip()
    args = text.split()
    channel_id = command["channel_id"]

    # No args → company picker buttons (full-period report on click)
    if not args:
        buttons = [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": company["name"], "emoji": True},
                "action_id": f"company_report_{key}",
                "value": key,
            }
            for key, company in COMPANIES.items()
        ]
        respond(
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "🏢 *분석할 회사를 선택하세요* (버튼 = 전체 기간)\n"
                            "기간 지정: `/company_analyze <회사> <시작YYYYMMDD> <종료YYYYMMDD>`\n"
                            "예: `/company_analyze skild 20260201 20260401`"
                        ),
                    },
                },
                {"type": "actions", "elements": buttons},
            ]
        )
        return

    # company + optional [start] [end]
    company_key = resolve_company(args[0])
    if not company_key or company_key not in COMPANIES:
        valid = ", ".join(f"`{c['prefix']}`" for c in COMPANIES.values())
        respond(
            f"❌ 회사를 찾지 못했어요: `{args[0]}`\n"
            f"사용법: `/company_analyze <회사> [시작YYYYMMDD] [종료YYYYMMDD]`\n"
            f"회사: {valid}"
        )
        return

    start = end = None
    if len(args) >= 2:
        start = args[1]
        end = args[2] if len(args) >= 3 else datetime.now().strftime("%Y%m%d")
        for ds, label in [(start, "시작"), (end, "종료")]:
            if len(ds) != 8 or not ds.isdigit():
                respond(f"❌ {label}날짜 형식이 잘못되었습니다: `{ds}` (YYYYMMDD)")
                return
        if start > end:
            respond("❌ 시작날짜가 종료날짜보다 뒤입니다.")
            return

    run_company_report(app.client, channel_id, company_key, start, end)


def build_metric_card_blocks(m):
    """Deterministic metric card (Block Kit) from computed metrics."""
    p, v, hc = m["period"], m["velocity"], m["headcount"]

    head = {
        "type": "header",
        "text": {"type": "plain_text", "text": f"📊 {m['company']} 경쟁사 분석", "emoji": True},
    }
    ctx_txt = (
        f"*구간:* {_fmt_date(p['actual_start'])} → {_fmt_date(p['actual_end'])} · "
        f"스냅샷 {p['n_snapshots']}개"
    )
    if p["clamped"]:
        ctx_txt += "  _(요청 범위 내 실제 데이터 구간)_"
    ctx = {"type": "context", "elements": [{"type": "mrkdwn", "text": ctx_txt}]}

    lines = []
    if p["single"]:
        lines.append("⚠️ *스냅샷 1개* — 현황 스냅만 (추세·속도 분석 불가)")
        lines.append(f"*👥 현재 포지션* {hc['end']}개")
    else:
        lines.append(f"*👥 채용 규모* {hc['start']} → {hc['end']}  (순 {hc['net']:+d}, 기간 최대 {hc['peak']})")
        opw = f"{v['opens_per_week']:.1f}/주" if v["opens_per_week"] is not None else "?"
        lines.append(
            f"*⚡ 채용 속도* +{v['opens']} / -{v['closes']} (순 {v['net']:+d}) · "
            f"오픈 {opw} · JD재작성 {v['modifies']} · 재오픈 {v['reopens']}"
        )

    fm = m["function_mix"]
    func_str = _mix_line(fm["end"]) or "없음"
    if not p["single"]:
        deltas = {k: d for k, d in fm["delta"].items() if d}
        if deltas:
            top_deltas = sorted(deltas.items(), key=lambda x: -abs(x[1]))[:4]
            func_str += "  (변화: " + ", ".join(f"{k} {d:+d}" for k, d in top_deltas) + ")"
    lines.append(f"*🧩 직무 믹스* {func_str}")
    lines.append(f"*🎚️ 시니어리티* {_mix_line(m['seniority_mix']) or '없음'}")

    g = m["geo"]
    if g["has_geo"]:
        gl = f"*🌍 지역* {g['distinct']}곳 · " + ", ".join(f"{loc}({n})" for loc, n in g["top"])
        if g["new"]:
            gl += f" · _신규:_ {', '.join(g['new'])}"
        lines.append(gl)

    if m["comp"]["items"]:
        lines.append(f"*💰 보상* {len(m['comp']['items'])}건 공개 (equity {m['comp']['equity_count']}건)")

    lg = m["longevity"]
    if lg["closed_median_days"] is not None:
        ll = f"*⏳ 공고 수명* 마감 기준 중앙값 {lg['closed_median_days']:.0f}일 (n={lg['n_closed_with_days']})"
        if lg["oldest_open"]:
            t, d = lg["oldest_open"][0]
            ll += f" · 가장 오래 열림: {t} ({d}일)"
        lines.append(ll)

    b = m["blog"]
    lines.append(f"*📝 블로그/리서치* 기간 발행 {len(b['published'])}건 · 수정 {len(b['edits'])}건")
    if b["themes"]:
        lines.append("   _테마:_ " + ", ".join(f"{t}({n})" for t, n in b["themes"][:6]))
    for post in b["published"][:6]:
        url = post.get("url", "")
        title = f"<{url}|{post['title']}>" if url else post["title"]
        lines.append(f"   • [{post['date']}] {title}")

    blocks = [head, ctx, {"type": "divider"}]
    for chunk in chunk_mrkdwn("\n".join(lines)):
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})
    return blocks


def run_company_report(client, channel_id, company_key, start, end):
    """Run the full metric-card + AI-narrative report for one company and post to Slack."""
    company = COMPANIES[company_key]
    name = company["name"]
    label = "전체 기간" if not start else f"{_fmt_date(start)} ~ {_fmt_date(end)}"
    # Root message — the metric card + AI narrative thread under it.
    root_resp = client.chat_postMessage(
        channel=channel_id,
        text=f"🔍 *{name}* {label} 분석 중... _결과는 이 스레드에 ⬇️_",
        unfurl_links=False,
        unfurl_media=False,
    )
    thread_ts = root_resp["ts"]

    metrics, err = analyze(company, start, end)
    if err:
        if err.get("reason") == "empty_range":
            a0, a1 = err["available"]
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=f"❌ 해당 기간에 *{name}* 스냅샷이 없습니다.\n사용 가능 범위: `{a0} ~ {a1}`",
            )
        else:
            client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=f"❌ *{name}* 데이터가 없습니다.")
        return

    # Metric card as the first thread reply.
    client.chat_postMessage(
        channel=channel_id,
        thread_ts=thread_ts,
        text=f"📊 {name} 분석",
        blocks=build_metric_card_blocks(metrics),
        unfurl_links=False,   # suppress automatic link-preview cards
        unfurl_media=False,
    )

    # AI narrative posted as further thread replies under the root.
    analysis = run_claude_analysis(build_ai_prompt(metrics))
    if analysis:
        for chunk in chunk_mrkdwn(f"🤖 *AI 해설 — {name}*\n\n{analysis}"):
            client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=chunk,
                                    unfurl_links=False, unfurl_media=False)
    else:
        client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text="⚠️ AI 해설 생성에 실패했습니다.")


# Register button action handlers for each company (button = full-period report)
for _company_key in COMPANIES:
    def _make_handler(ckey):
        @app.action(f"company_report_{ckey}")
        def handle_action(ack, body, client):
            ack()
            channel_id = body["channel"]["id"]
            run_company_report(client, channel_id, ckey, None, None)

    _make_handler(_company_key)


# ==========================================
# /deleted_jd command — browse no-longer-posted positions and read their full JD
# ==========================================
#
# 3-step flow (company first avoids cross-company title collisions; id-deduped
# list avoids same-title-different-job collisions within a company):
#   /deleted_jd            -> company picker buttons
#   pick a company         -> static_select of that company's deleted positions
#   pick a position        -> full stored JD body (verbatim, no AI)
#
# Read-only over existing snapshots — touches no crawler/daily-pipeline code.
# The select carries an INDEX (not the id) because some ids exceed Slack's
# 75-char option-value limit; handlers re-derive the deterministic list to map
# the index back to a position.


@app.command("/deleted_jd")
def handle_deleted_jd(ack, respond, command):
    ack()

    args = command.get("text", "").strip().split()

    # No args → company picker buttons.
    if not args:
        buttons = [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": company["name"], "emoji": True},
                "action_id": f"deleted_company_{key}",
                "value": key,
            }
            for key, company in COMPANIES.items()
        ]
        respond(
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "🗑️ *삭제된(현재 미게시) 공고를 조회할 회사를 선택하세요*\n"
                            "또는 바로: `/deleted_jd <회사>`  (예: `/deleted_jd dyna`)"
                        ),
                    },
                },
                {"type": "actions", "elements": buttons},
            ]
        )
        return

    company_key = resolve_company(args[0])
    if not company_key or company_key not in COMPANIES:
        valid = ", ".join(f"`{c['prefix']}`" for c in COMPANIES.values())
        respond(
            f"❌ 회사를 찾지 못했어요: `{args[0]}`\n"
            f"사용법: `/deleted_jd [회사]`\n회사: {valid}"
        )
        return

    _post_deleted_picker(app.client, command["channel_id"], company_key)


def _post_deleted_picker(client, channel_id, company_key):
    """Post a static_select of a company's deleted (no-longer-posted) positions."""
    company = COMPANIES[company_key]
    name = company["name"]
    items = deleted_positions(company)

    if not items:
        client.chat_postMessage(
            channel=channel_id,
            text=f"✅ *{name}*: 기록상 삭제된(현재 미게시) 공고가 없습니다.",
        )
        return

    # Compact root in the channel; the readable list + dropdown + every opened JD
    # body all thread under it, so the channel timeline stays a single line.
    note = "" if len(items) <= 100 else f"  _(최근 100개만 표시 / 총 {len(items)}개)_"
    root_resp = client.chat_postMessage(
        channel=channel_id,
        text=f"🗑️ *{name}* — 삭제된(현재 미게시) 공고 *{len(items)}개*{note}\n_목록·본문은 이 스레드에 ⬇️_",
        unfurl_links=False,
        unfurl_media=False,
    )
    thread_ts = root_resp["ts"]

    # Slack caps a static_select at 100 options and each option label at 75 chars.
    shown = items[:100]

    # Full-width readable list (numbered) so the title + deletion date + location
    # are always visible — the narrow dropdown alone truncates long titles and
    # hides the date, which is exactly the info the user wants to see at a glance.
    lines = []
    for idx, m in enumerate(shown):
        loc = f"  ·  📍 {m['location']}" if m.get("location") else ""
        lines.append(
            f"`{idx + 1:>2}.`  *{m['title']}*  ·  🗓️ 삭제 {_fmt_date(m['last_seen'])}{loc}"
        )

    # Dropdown options: text = numbered title, description = date+location. The
    # `description` line shows beneath each option in the menu so the deletion
    # date stays visible even when the title fills the 75-char text limit.
    options = []
    for idx, m in enumerate(shown):
        txt = f"{idx + 1}. {m['title']}"[:75]
        desc = f"🗓️ 삭제 {_fmt_date(m['last_seen'])}"
        if m.get("location"):
            desc += f" · {m['location']}"
        options.append({
            "text": {"type": "plain_text", "text": txt, "emoji": True},
            "description": {"type": "plain_text", "text": desc[:75], "emoji": True},
            "value": str(idx),
        })

    # Readable list (chunked to respect the 3000-char section limit).
    blocks = []
    for chunk in chunk_mrkdwn("\n".join(lines)):
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "👇 *조회할 공고를 선택하세요* (번호로 위 목록과 대조)"},
        "accessory": {
            "type": "static_select",
            "placeholder": {"type": "plain_text", "text": "공고 선택", "emoji": True},
            "action_id": f"deleted_pick_{company_key}",
            "options": options,
        },
    })
    # List + dropdown as a thread reply under the root.
    client.chat_postMessage(
        channel=channel_id,
        thread_ts=thread_ts,
        text=f"🗑️ {name} 삭제된 공고",
        blocks=blocks,
        unfurl_links=False,
        unfurl_media=False,
    )


def _post_deleted_jd_body(client, channel_id, company_key, idx, thread_ts=None):
    """Post the full stored JD body for the idx-th deleted position (verbatim).

    Posted as thread replies under the root (thread_ts) so the list, dropdown,
    and every JD you open all stay grouped in one thread off the channel."""
    company = COMPANIES[company_key]
    name = company["name"]
    items = deleted_positions(company)

    if idx < 0 or idx >= len(items):
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="⚠️ 선택한 공고를 찾을 수 없습니다 (목록이 갱신되었을 수 있어요). `/deleted_jd`로 다시 시도해주세요.",
        )
        return

    m = items[idx]
    record, last_seen = get_position_record(company, m["id"])
    if not record:
        client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text="⚠️ 공고 본문을 찾지 못했습니다.")
        return

    title = record.get("title", m["title"])
    loc = record.get("location", "")
    comp = record.get("compensation", "")
    url = record.get("url", "")
    desc = record.get("description", "").strip() or "_(저장된 본문이 없습니다)_"

    meta_parts = []
    if loc:
        meta_parts.append(f"📍 {loc}")
    if comp:
        meta_parts.append(f"💰 {comp}")
    meta_parts.append(
        f"🗓️ 마지막 노출 {_fmt_date(last_seen)} · 첫 노출 {_fmt_date(m['first_seen'])}"
    )
    if url:
        meta_parts.append(f"🔗 <{url}|원본 링크>")

    header = f"🗑️ *{title}*  ·  _{name}_\n" + "  ·  ".join(meta_parts) + "\n\n" + desc

    for chunk in chunk_mrkdwn(header):
        client.chat_postMessage(
            channel=channel_id, thread_ts=thread_ts, text=chunk,
            unfurl_links=False, unfurl_media=False,
        )


# Register per-company action handlers (button = pick company, select = pick JD).
for _deleted_key in COMPANIES:
    def _make_deleted_handlers(ckey):
        @app.action(f"deleted_company_{ckey}")
        def handle_deleted_company(ack, body, client):
            ack()
            _post_deleted_picker(client, body["channel"]["id"], ckey)

        @app.action(f"deleted_pick_{ckey}")
        def handle_deleted_pick(ack, body, client):
            ack()
            value = body["actions"][0]["selected_option"]["value"]
            # Thread the JD body under the SAME root as the list+dropdown. The
            # dropdown message is itself a thread reply, so its `thread_ts` points
            # to the root; fall back to its own ts if it isn't threaded.
            msg = body.get("message", {})
            thread_ts = msg.get("thread_ts") or msg.get("ts")
            _post_deleted_jd_body(client, body["channel"]["id"], ckey, int(value), thread_ts)

    _make_deleted_handlers(_deleted_key)


# ==========================================
# Entry point
# ==========================================

if __name__ == "__main__":
    logger.info("🚀 Scouting Bot starting (Socket Mode)...")
    handler = SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN"))
    handler.start()
