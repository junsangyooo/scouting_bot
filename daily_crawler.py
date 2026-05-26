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
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from slack_sdk import WebClient

load_dotenv()

# Add company_crawler to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'company_crawler'))

from physical_intelligence.main import run as run_pi
from skild_ai.main import run as run_skild
from dyna.main import run as run_dyna
from generalist_ai.main import run as run_generalist

COMPANIES = {
    "physical_intelligence": ("Physical Intelligence", run_pi, "pi"),
    "skild_ai": ("Skild AI", run_skild, "skild"),
    "dyna": ("DYNA", run_dyna, "dyna"),
    "generalist_ai": ("Generalist AI", run_generalist, "generalist"),
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

    try:
        # Call Claude CLI
        print(f"[INFO] Sending analysis request to Claude...")
        result = subprocess.run(
            ['claude', '-p', '--model', 'sonnet'],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0 and result.stdout.strip():
            analysis_text = result.stdout.strip()

            # Save analysis to file for debugging
            analysis_dir = Path("logs/analysis")
            analysis_dir.mkdir(parents=True, exist_ok=True)
            analysis_file = analysis_dir / f"{company_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            analysis_file.write_text(analysis_text, encoding='utf-8')
            print(f"[INFO] Analysis saved to {analysis_file}")

            return analysis_text
        else:
            print(f"[ERROR] Claude CLI failed for {company_name}: {result.stderr}")
            return None

    except subprocess.TimeoutExpired:
        print(f"[ERROR] Claude CLI timeout for {company_name}")
        return None
    except Exception as e:
        print(f"[ERROR] Failed to analyze {company_name}: {e}")
        return None


def format_slack_message(results):
    """Format crawling results for Slack with detailed status for all 7 sections"""

    # Slack Block Kit format
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🤖 Daily Company Crawler Report",
                "emoji": True
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"*Date:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S KST')}"
                }
            ]
        },
        {
            "type": "divider"
        }
    ]

    has_updates = False

    for result in results:
        if not result:
            continue

        company = result.get("company", "Unknown")
        company_text = f"*{company}*\n"

        if "error" in result:
            company_text += f"❌ *Error:* {result['error']}\n"
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": company_text
                }
            })
            blocks.append({"type": "divider"})
            continue

        # Blog/Research updates
        blog_data = result.get("blog") or result.get("research", {})
        if blog_data:
            status = blog_data.get("status", "initialized")
            if status == "updated":
                has_updates = True
                added = blog_data.get("added", [])
                removed = blog_data.get("removed", [])
                updated = blog_data.get("updated", [])

                company_text += "- *Blog:*\n"
                if added:
                    company_text += "  - *Added:*\n"
                    for post in added:
                        title = post.get('title', 'Untitled')
                        url = post.get('url', '')
                        if url:
                            company_text += f"    • <{url}|{title}>\n"
                        else:
                            company_text += f"    • {title}\n"
                if removed:
                    company_text += "  - *Removed:*\n"
                    for post in removed:
                        title = post.get('title', 'Untitled')
                        url = post.get('url', '')
                        if url:
                            company_text += f"    • <{url}|{title}>\n"
                        else:
                            company_text += f"    • {title}\n"
                if updated:
                    company_text += "  - *Updated:*\n"
                    for post in updated:
                        title = post.get('title', 'Untitled')
                        url = post.get('url', '')
                        if url:
                            company_text += f"    • <{url}|{title}>\n"
                        else:
                            company_text += f"    • {title}\n"
            else:
                company_text += "- *Blog:* Checked\n"

        # Position updates
        pos_data = result.get("position", {})
        if pos_data:
            status = pos_data.get("status", "initialized")
            if status == "updated":
                has_updates = True
                added = pos_data.get("added", [])
                removed = pos_data.get("removed", [])
                updated = pos_data.get("updated", [])

                company_text += "- *Career:*\n"
                if added:
                    company_text += "  - *Added:*\n"
                    for pos in added:
                        title = pos.get('title', 'Untitled')
                        url = pos.get('url', '')
                        if url:
                            company_text += f"    • <{url}|{title}>\n"
                        else:
                            company_text += f"    • {title}\n"
                if removed:
                    company_text += "  - *Removed:*\n"
                    for pos in removed:
                        title = pos.get('title', 'Untitled')
                        url = pos.get('url', '')
                        if url:
                            company_text += f"    • <{url}|{title}>\n"
                        else:
                            company_text += f"    • {title}\n"
                if updated:
                    company_text += "  - *Updated:*\n"
                    for pos in updated:
                        title = pos.get('title', 'Untitled')
                        url = pos.get('url', '')
                        if url:
                            company_text += f"    • <{url}|{title}>\n"
                        else:
                            company_text += f"    • {title}\n"
            else:
                company_text += "- *Career:* Checked\n"

        # Add AI analysis if available
        analysis = result.get("analysis")
        if analysis:
            company_text += "\n📊 *AI Analysis*\n"
            company_text += f"{analysis}\n"

        # Add company section
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": company_text
            }
        })

        # Add blank line (divider) after each company
        blocks.append({"type": "divider"})

    # Summary
    if not has_updates:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "✅ *Summary:* No significant changes detected"
            }
        })
    else:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "🔔 *Summary:* Updates detected! Check details above."
            }
        })

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
        )

        if response["ok"]:
            print(f"\n✅ Slack notification sent to channel {channel_id}!")
            return True
        else:
            print(f"\n❌ Failed: {response.get('error')}")
            return False

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
            json=message,
            headers={'Content-Type': 'application/json'}
        )
        if response.status_code == 200:
            print("\n✅ Slack notification sent via webhook!")
            return True
        else:
            print(f"\n❌ Failed: {response.status_code} {response.text}")
            return False
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
