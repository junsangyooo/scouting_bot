#!/usr/bin/env python3
"""
Daily Company Crawler with Slack Notification
Automatically runs the crawler and sends formatted results to Slack
"""

import sys
import json
import os
import shutil
from datetime import datetime
from io import StringIO
import requests
from pathlib import Path
from dotenv import load_dotenv
from slack_sdk import WebClient

from claude_cli import run_claude

load_dotenv()

# Add company_crawler to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'company_crawler'))

from physical_intelligence.main import run as run_pi
from skild_ai.main import run as run_skild
from dyna.main import run as run_dyna
from generalist_ai.main import run as run_generalist
from sunday.main import run as run_sunday
from genesis.main import run as run_genesis
from rhoda.main import run as run_rhoda

COMPANIES = {
    "physical_intelligence": ("Physical Intelligence", run_pi, "pi"),
    "skild_ai": ("Skild AI", run_skild, "skild"),
    "dyna": ("DYNA", run_dyna, "dyna"),
    "generalist_ai": ("Generalist AI", run_generalist, "generalist"),
    "sunday": ("Sunday Robotics", run_sunday, "sunday"),
    "genesis": ("Genesis AI", run_genesis, "genesis"),
    "rhoda": ("Rhoda AI", run_rhoda, "rhoda"),
}

# Public-facing pages for each company's blog/research + careers. Each company's
# thread reply links to these ("채용 페이지 보기" / "블로그/리서치 페이지 보기").
# Keyed by display name (that's what each crawler result carries).
COMPANY_LINKS = {
    "Physical Intelligence": {"career": "https://www.pi.website/join-us", "blog": "https://www.pi.website/blog"},
    "Skild AI": {"career": "https://www.skild.ai/career", "blog": "https://www.skild.ai/blogs"},
    "DYNA": {"career": "https://jobs.ashbyhq.com/dyna-robotics", "blog": "https://www.dyna.co/research"},
    "Generalist AI": {"career": "https://generalistai.com/careers", "blog": "https://generalistai.com/blog"},
    "Sunday Robotics": {"career": "https://jobs.ashbyhq.com/sunday", "blog": "https://www.sunday.ai/journal"},
    "Genesis AI": {"career": "https://www.genesis.ai/careers", "blog": "https://www.genesis.ai/blog"},
    "Rhoda AI": {"career": "https://www.rhoda.ai/careers", "blog": "https://www.rhoda.ai/news"},
}

DATA_FILES = {
    "physical_intelligence": [
        "data/physical_intelligence/pi_positions.json",
        "data/physical_intelligence/pi_blog.json",
    ],
    "skild_ai": [
        "data/skild_ai/skild_positions.json",
        "data/skild_ai/skild_blog.json",
    ],
    "dyna": [
        "data/dyna/dyna_positions.json",
        "data/dyna/dyna_blog.json",
    ],
    "generalist_ai": [
        "data/generalist_ai/generalist_positions.json",
        "data/generalist_ai/generalist_blog.json",
    ],
    "sunday": [
        "data/sunday/sunday_positions.json",
        "data/sunday/sunday_blog.json",
    ],
    "genesis": [
        "data/genesis/genesis_positions.json",
        "data/genesis/genesis_blog.json",
    ],
    "rhoda": [
        "data/rhoda/rhoda_positions.json",
        "data/rhoda/rhoda_blog.json",
    ],
}


def save_daily_snapshots():
    """Copy each latest data file to a date-prefixed snapshot."""
    date_str = datetime.now().strftime("%Y%m%d")

    for company_key, file_paths in DATA_FILES.items():
        for file_path in file_paths:
            src = Path(file_path)
            if not src.exists():
                continue

            snapshot_name = f"{date_str}_{src.name}"
            snapshot_path = src.parent / snapshot_name

            if snapshot_path.exists():
                print(f"[INFO] Snapshot already exists: {snapshot_path}")
                continue

            shutil.copy2(str(src), str(snapshot_path))
            print(f"[INFO] Saved snapshot: {snapshot_path}")


def crawl_all_companies(purpose="all"):
    """Run crawler for all companies"""
    results = []

    for key, (name, runner, file_prefix) in COMPANIES.items():
        print(f"\n[INFO] Crawling {name}...")
        try:
            result = runner(purpose)

            # Analyze position changes if there are updates
            position_data = result.get("position", {})
            if position_data and position_data.get("status") == "updated":
                print(f"[INFO] Analyzing position changes for {name}...")
                analysis = analyze_position_changes(name, key, file_prefix, position_data)
                if analysis:
                    result["analysis"] = analysis
                    print(f"[INFO] Analysis completed for {name}")
                else:
                    # Career changes were detected but the AI narrative could not
                    # be generated (e.g. usage/rate limit). Flag it so the report
                    # posts a visible "분석 실패" note instead of silently omitting
                    # the thread reply — the change list still shows in the root.
                    result["analysis_failed"] = True
                    print(f"[WARN] AI analysis unavailable for {name}; report will note the failure")

            results.append(result)
            print(f"[INFO] {name} completed")
        except Exception as e:
            print(f"[ERROR] {name} failed: {e}")
            results.append({"company": name, "error": str(e)})

    return results


def analyze_position_changes(company_name, company_key, file_prefix, position_data):
    """
    Use Claude CLI to analyze position changes and generate insights.

    Args:
        company_name: Full company name (e.g., "Physical Intelligence")
        company_key: Company key for directory paths (e.g., "physical_intelligence")
        file_prefix: File prefix for data files (e.g., "pi")
        position_data: Position data from crawler result

    Returns:
        str: Analysis report in bullet point format, or None if no analysis needed
    """
    status = position_data.get("status", "")

    # Only analyze if there are actual changes
    if status != "updated":
        return None

    # Read full position data
    data_file = Path(f"data/{company_key}/{file_prefix}_positions.json")
    if not data_file.exists():
        return None

    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            full_positions = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to read position data for {company_name}: {e}")
        return None

    # Extract changes
    added = position_data.get("added", [])
    removed = position_data.get("removed", [])
    updated = position_data.get("updated", [])

    # Build analysis prompt (only send changes, not full position list)
    prompt = f"""다음은 {company_name}의 채용공고 변화 데이터입니다.

현재 전체 포지션 수: {len(full_positions)}개

=== 이번에 감지된 변화 ===
신규 추가: {len(added)}개
삭제됨: {len(removed)}개
업데이트됨: {len(updated)}개

추가된 포지션:
{json.dumps(added, ensure_ascii=False, indent=2)}

삭제된 포지션:
{json.dumps(removed, ensure_ascii=False, indent=2)}

업데이트된 포지션:
{json.dumps(updated, ensure_ascii=False, indent=2)}

=== 분석 요청 ===
위 데이터를 바탕으로 다음 형식으로 분석해주세요:

*형식 규칙:*
- *Slack mrkdwn 형식 사용* (중요!)
- Bold는 *텍스트* (별표 1개)
- ** 절대 사용하지 마세요
- 최대한 간결하고 핵심적인 불렛 포인트만
- 각 불렛은 한 줄로 요약
- 각 불렛 아래에 간결한 한줄 근거 (서브 불렛)
- 설명형 문장보다는 강조된 키워드와 수치 중심
- 놀랄만한 인사이트나 특이사항만 포함

*분석 항목:*
1. 🔍 주요 변화
2. 💡 핵심 인사이트
3. 📊 채용 트렌드

*출력 예시:*
🔍 주요 변화
• *Senior ML Engineer* 3개 포지션 신규 추가
  - 모두 robotics foundation model 경험 요구
• Hardware 관련 포지션 2개 삭제
  - 소프트웨어 중심으로 전환 신호

💡 핵심 인사이트
• *Production 단계 진입 가능성*
  - DevOps/MLOps 엔지니어 채용 시작
• *데이터 인프라 강화 중*
  - Data Engineer, ML Platform 포지션 추가

📊 채용 트렌드
• 전체 채용 규모 40% 증가
  - 이전 10개 → 현재 14개 포지션

간결하게 작성해주세요. 너무 길지 않게, 핵심만! *별표는 1개만* 사용하세요."""

    # Call Claude CLI (retries + rich diagnostics live in claude_cli.run_claude;
    # it returns None only after exhausting retries, which the caller surfaces as
    # a "분석 실패" thread note rather than silently dropping the analysis).
    print(f"[INFO] Sending analysis request to Claude...")
    analysis_text = run_claude(prompt, label=company_name, log=print)

    if not analysis_text:
        print(f"[ERROR] Claude analysis unavailable for {company_name} after retries")
        return None

    # Save analysis to file for debugging
    try:
        analysis_dir = Path("logs/analysis")
        analysis_dir.mkdir(parents=True, exist_ok=True)
        analysis_file = analysis_dir / f"{company_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        analysis_file.write_text(analysis_text, encoding='utf-8')
        print(f"[INFO] Analysis saved to {analysis_file}")
    except Exception as e:
        # A logging-only failure must not discard a good analysis.
        print(f"[WARN] Could not save analysis file for {company_name}: {e}")

    return analysis_text


def _chunk_mrkdwn(text, limit=2900):
    """Split a mrkdwn string into chunks under Slack's 3000-char per-block limit.

    Splits on line boundaries; any single line longer than the limit is
    hard-split by character so no chunk ever exceeds the limit.
    """
    if len(text) <= limit:
        return [text]

    chunks = []
    cur = ""
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


def _blog_data_of(result):
    """Blog stream regardless of key naming ("blog" vs "research")."""
    return result.get("blog") or result.get("research") or {}


def _label(text, url):
    """Slack mrkdwn bold label, linked to `url` when available."""
    return f"*<{url}|{text}>:*" if url else f"*{text}:*"


def _render_section(label_md, data):
    """Render one '- {label}' line for the main report.

    '... Checked' when unchanged, else the label followed by nested
    Added/Removed/Updated bullet lists with linked titles.
    """
    if data.get("status") != "updated":
        return f"- {label_md} Checked\n"
    out = f"- {label_md}\n"
    for key, sub in (("added", "Added"), ("removed", "Removed"), ("updated", "Updated")):
        items = data.get(key, [])
        if not items:
            continue
        out += f"  - *{sub}:*\n"
        for it in items:
            title = it.get("title", "Untitled")
            url = it.get("url", "")
            out += f"    • <{url}|{title}>\n" if url else f"    • {title}\n"
    return out


def build_analysis_thread_blocks(result):
    """Decorated Block Kit blocks for ONE company's AI Analysis thread reply.

    The main report already carries the per-company Blog/Career change list, so
    the thread reply holds only the AI narrative (which exists for career
    changes). If the narrative failed to generate despite detected career
    changes (`analysis_failed`), a short failure note is posted instead.
    Returns None when there is nothing to post (no changes / unchanged company).
    """
    analysis = result.get("analysis")
    company = result.get("company", "Unknown")
    links = COMPANY_LINKS.get(company, {})

    if not analysis:
        # No AI narrative. Stay silent for unchanged companies, but if career
        # changes WERE detected and analysis failed, post a visible note so the
        # reader doesn't mistake "no thread reply" for "no change".
        if not result.get("analysis_failed"):
            return None
        blocks = [
            {"type": "header",
             "text": {"type": "plain_text", "text": f"⚠️ {company} · AI 분석 실패", "emoji": True}},
            {"type": "section", "text": {"type": "mrkdwn", "text": (
                "채용 변화는 감지됐으나 AI 분석 생성에 실패했습니다 "
                "(재시도 후에도 실패 — 사용량/레이트 한도 가능성).\n"
                "변경 항목은 위 리포트의 *Career* 목록을 참고하세요. "
                "필요 시 `/company_analyze` 로 수동 분석을 돌릴 수 있습니다.")}},
        ]
        if links.get("career"):
            blocks.append({"type": "context", "elements": [
                {"type": "mrkdwn", "text": f"🔗 <{links['career']}|채용 페이지 보기>"}]})
        return blocks

    blocks = [{
        "type": "header",
        "text": {"type": "plain_text", "text": f"📊 {company} · AI Analysis", "emoji": True},
    }]
    for chunk in _chunk_mrkdwn(analysis):
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})
    if links.get("career"):
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"🔗 <{links['career']}|채용 페이지 보기>"}]})
    return blocks


def format_slack_message(results):
    """Main report (root message): per-company Blog/Career change list.

    The AI analysis is NOT inlined here — it is posted as a decorated thread
    reply under this message (see build_analysis_thread_blocks /
    send_slack_notification) so the root stays focused on what changed.
    """
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🤖 Daily Company Crawler Report", "emoji": True},
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"*Date:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S KST')}"}
            ],
        },
        {"type": "divider"},
    ]

    has_updates = False
    for result in results:
        if not result:
            continue
        company = result.get("company", "Unknown")
        links = COMPANY_LINKS.get(company, {})
        company_text = f"*{company}*\n"

        if "error" in result:
            company_text += f"❌ *Error:* {result['error']}\n"
            for chunk in _chunk_mrkdwn(company_text):
                blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})
            blocks.append({"type": "divider"})
            continue

        blog_data = _blog_data_of(result)
        if blog_data:
            if blog_data.get("status") == "updated":
                has_updates = True
            company_text += _render_section(_label("Blog", links.get("blog")), blog_data)

        pos_data = result.get("position") or {}
        if pos_data:
            if pos_data.get("status") == "updated":
                has_updates = True
            company_text += _render_section(_label("Career", links.get("career")), pos_data)

        # Split into multiple blocks if it exceeds Slack's 3000-char per-block
        # limit (e.g. a brand-new company whose whole list lands in "Added").
        for chunk in _chunk_mrkdwn(company_text):
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})
        blocks.append({"type": "divider"})

    if not has_updates:
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": "✅ *Summary:* No significant changes detected"}})
    else:
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": "🔔 *Summary:* Updates detected! AI 분석은 각 기업 쓰레드 댓글을 확인하세요."}})

    return {"blocks": blocks}


def send_slack_notification(results):
    """Send formatted results to Slack via Bot Token"""
    channel_id = os.environ.get('SLACK_CHANNEL_ID', 'C0AR5NXH160')
    bot_token = os.environ.get('SLACK_BOT_TOKEN')

    if not bot_token:
        print("❌ SLACK_BOT_TOKEN not set, falling back to webhook")
        return send_slack_notification_webhook(results)

    try:
        client = WebClient(token=bot_token)
        message = format_slack_message(results)

        response = client.chat_postMessage(
            channel=channel_id,
            text="🤖 Daily Company Crawler Report",
            blocks=message["blocks"],
            unfurl_links=False,   # suppress automatic link-preview cards
            unfurl_media=False,
        )

        if not response["ok"]:
            print(f"\n❌ Failed: {response.get('error')}")
            return False

        print(f"\n✅ Slack notification sent to channel {channel_id}!")

        # Post each company's AI analysis as a decorated thread reply, keeping
        # the per-company change list in the root message above.
        thread_ts = response["ts"]
        for result in results:
            if not result or "error" in result:
                continue
            blocks = build_analysis_thread_blocks(result)
            if not blocks:
                continue
            company = result.get("company", "Unknown")
            try:
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=f"📊 {company} · AI Analysis",
                    blocks=blocks,
                    unfurl_links=False,
                    unfurl_media=False,
                )
            except Exception as e:
                print(f"⚠️  Failed to post thread reply for {company}: {e}")
        return True

    except Exception as e:
        print(f"\n❌ Error sending Slack notification: {e}")
        import traceback
        traceback.print_exc()
        return False


def send_slack_notification_webhook(results):
    """Fallback: Send via webhook (legacy)"""
    webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
    if not webhook_url:
        print("❌ No SLACK_WEBHOOK_URL either, skipping notification")
        return False

    try:
        message = format_slack_message(results)
        response = requests.post(
            webhook_url,
            json={**message, "unfurl_links": False, "unfurl_media": False},
            headers={'Content-Type': 'application/json'}
        )
        if response.status_code != 200:
            print(f"\n❌ Failed: {response.status_code} {response.text}")
            return False

        print("\n✅ Slack notification sent via webhook!")

        # Webhooks can't thread, so post each company's AI analysis as a
        # separate follow-up message instead of a thread reply.
        for result in results:
            if not result or "error" in result:
                continue
            blocks = build_analysis_thread_blocks(result)
            if not blocks:
                continue
            requests.post(
                webhook_url,
                json={"blocks": blocks, "unfurl_links": False, "unfurl_media": False},
                headers={'Content-Type': 'application/json'},
            )
        return True
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def main():
    """Main execution function"""

    # Check if running in test mode
    test_mode = os.environ.get('TEST_MODE', '').lower() in ['true', '1', 'yes']

    print("=" * 60)
    print(f"🚀 Starting Daily Company Crawler")
    print(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S KST')}")
    print("=" * 60)

    # Run crawler
    results = crawl_all_companies(purpose="all")

    # Save daily snapshots
    print("\n" + "=" * 60)
    print("💾 Saving daily snapshots...")
    print("=" * 60)
    save_daily_snapshots()

    # Print results to console
    print("\n" + "=" * 60)
    print("📊 CRAWL RESULTS")
    print("=" * 60)

    for result in results:
        if result:
            company = result.get("company", "Unknown")
            print(f"\n[{company}]")
            if "error" in result:
                print(f"  ❌ Error: {result['error']}")
            else:
                print(f"  ✅ Success")

    # Send Slack notification
    if not test_mode:
        print("\n" + "=" * 60)
        print("📤 Sending Slack Notification...")
        print("=" * 60)

        send_slack_notification(results)
    else:
        print("\n" + "=" * 60)
        print("⚠️  TEST MODE: Skipping Slack notification")
        print("=" * 60)

    print("\n✅ Daily crawler completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
