#!/usr/bin/env python3
"""
Scouting Bot — Slack Bot (Socket Mode)
Handles /analyze slash command and can send daily reports.
"""

import json
import os
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
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
    },
    "skild_ai": {
        "name": "Skild AI",
        "prefix": "skild",
        "data_dir": BASE_DIR / "data" / "skild_ai",
        "files": ["positions", "blog"],
    },
    "dyna": {
        "name": "DYNA",
        "prefix": "dyna",
        "data_dir": BASE_DIR / "data" / "dyna",
        "files": ["positions", "blog"],
    },
    "generalist_ai": {
        "name": "Generalist AI",
        "prefix": "generalist",
        "data_dir": BASE_DIR / "data" / "generalist_ai",
        "files": ["positions", "blog"],
    },
    "sunday": {
        "name": "Sunday Robotics",
        "prefix": "sunday",
        "data_dir": BASE_DIR / "data" / "sunday",
        "files": ["positions", "blog"],
    },
    "genesis": {
        "name": "Genesis AI",
        "prefix": "genesis",
        "data_dir": BASE_DIR / "data" / "genesis",
        "files": ["positions", "blog"],
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

    prompt = f"""다음은 {formatted_start} ~ {formatted_end} 기간 동안 3개 로보틱스 회사의 변화 데이터입니다.

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
1. 📋 기간 요약 (각 회사별 포지션/블로그/멤버 수 변화)
2. 🔍 주요 변화 (추가/삭제된 포지션, 새 블로그, 멤버 변동)
3. 💡 핵심 인사이트 (채용 전략 변화, 조직 방향성 등)
4. ⚠️ 특이사항 (Unusual한 패턴, 급격한 변화 등)

JD(Job Description) 변경이 있는 경우, 변경 내용의 핵심을 요약해주세요.
간결하게 작성해주세요. 핵심만! *별표는 1개만* 사용하세요."""

    return prompt


def run_claude_analysis(prompt):
    """Run Claude CLI to analyze the data."""
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", "sonnet"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            logger.error(f"Claude CLI failed: {result.stderr}")
            return None
    except subprocess.TimeoutExpired:
        logger.error("Claude CLI timeout")
        return None
    except Exception as e:
        logger.error(f"Claude CLI error: {e}")
        return None


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

    # Build summary message
    summary_blocks = build_summary_blocks(start_date, end_date, results)
    app.client.chat_postMessage(
        channel=command["channel_id"],
        text=f"📊 {formatted_start} ~ {formatted_end} 분석 결과",
        blocks=summary_blocks,
    )

    # Run Claude analysis
    prompt = build_analysis_prompt(start_date, end_date, results)
    analysis = run_claude_analysis(prompt)

    if analysis:
        app.client.chat_postMessage(
            channel=command["channel_id"],
            text=f"🤖 *AI 분석 ({formatted_start} ~ {formatted_end})*\n\n{analysis}",
        )
    else:
        app.client.chat_postMessage(
            channel=command["channel_id"],
            text="⚠️ AI 분석 생성에 실패했습니다.",
        )


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
        text = f"*{company_name}*\n"

        for file_type in ["positions", "blog"]:
            data = result.get(file_type)
            if not data:
                continue

            status = data.get("status", "")
            label = {"positions": "Career", "blog": "Blog"}.get(file_type, file_type)

            if status == "missing":
                text += f"• *{label}:* ⚠️ 데이터 없음\n"
            elif status == "checked":
                text += f"• *{label}:* ✅ 변경 없음\n"
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

                text += f"• *{label}:* {', '.join(parts)}\n"

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
    client.chat_postMessage(channel=channel_id, text=f"🔍 *{name}* {label} 분석 중... 잠시만 기다려주세요.")

    metrics, err = analyze(company, start, end)
    if err:
        if err.get("reason") == "empty_range":
            a0, a1 = err["available"]
            client.chat_postMessage(
                channel=channel_id,
                text=f"❌ 해당 기간에 *{name}* 스냅샷이 없습니다.\n사용 가능 범위: `{a0} ~ {a1}`",
            )
        else:
            client.chat_postMessage(channel=channel_id, text=f"❌ *{name}* 데이터가 없습니다.")
        return

    client.chat_postMessage(
        channel=channel_id,
        text=f"📊 {name} 분석",
        blocks=build_metric_card_blocks(metrics),
    )

    analysis = run_claude_analysis(build_ai_prompt(metrics))
    if analysis:
        for chunk in chunk_mrkdwn(f"🤖 *AI 해설 — {name}*\n\n{analysis}"):
            client.chat_postMessage(channel=channel_id, text=chunk)
    else:
        client.chat_postMessage(channel=channel_id, text="⚠️ AI 해설 생성에 실패했습니다.")


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
# Entry point
# ==========================================

if __name__ == "__main__":
    logger.info("🚀 Scouting Bot starting (Socket Mode)...")
    handler = SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN"))
    handler.start()
