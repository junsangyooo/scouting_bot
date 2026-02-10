# 🤖 Daily Company Crawler - 자동화 설정 가이드

매일 아침 8시에 자동으로 회사 크롤링을 실행하고 결과를 Slack으로 받는 시스템입니다.

## 📋 목차

1. [설치된 파일](#설치된-파일)
2. [Slack Webhook 설정](#slack-webhook-설정)
3. [환경 변수 설정](#환경-변수-설정)
4. [Cron 작업 설정](#cron-작업-설정)
5. [수동 테스트](#수동-테스트)
6. [문제 해결](#문제-해결)

---

## 📁 설치된 파일

```
scouting_bot/
├── daily_crawler.py           # 메인 자동화 스크립트
├── run_daily_crawler.sh        # Bash 실행 스크립트 (Git 자동 커밋/푸쉬 포함)
├── setup_cron.sh              # Cron 자동 설정 스크립트
├── .env.example               # 환경 변수 예시
├── logs/                      # 실행 로그 저장 (자동 생성)
└── .venv/                     # Python 가상환경
```

## 🔄 자동 Git 커밋/푸쉬

크롤링 후 `data/` 디렉토리에 변경사항이 있으면 **자동으로 GitHub에 커밋 및 푸쉬**됩니다:

1. **변경 감지**: `data/` 폴더의 JSON 파일 변경 확인
2. **자동 커밋**: 타임스탬프와 함께 커밋 메시지 생성
3. **자동 푸쉬**: GitHub에 자동으로 푸쉬

**커밋 메시지 형식**:
```
Auto-update company data - 2026-02-10 08:00:15 KST

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

이 기능은 `run_daily_crawler.sh` 스크립트에 내장되어 있어 별도 설정이 필요 없습니다.

---

## 🔧 Slack Webhook 설정

### 1단계: Slack Incoming Webhook 생성

1. https://api.slack.com/apps 접속
2. **"Create New App"** 클릭 → **"From scratch"** 선택
3. 앱 이름 입력 (예: `Company Crawler Bot`)
4. Workspace 선택
5. 왼쪽 메뉴에서 **"Incoming Webhooks"** 클릭
6. **"Activate Incoming Webhooks"** 토글을 ON으로 변경
7. **"Add New Webhook to Workspace"** 클릭
8. 메시지를 받을 채널 선택 (예: `#company-updates` 또는 DM)
9. **Webhook URL 복사** (예: `https://hooks.slack.com/services/T00000000/B00000000/XXXX...`)

---

## 🔐 환경 변수 설정

### 방법 1: ~/.bashrc에 영구 저장 (권장)

```bash
# Slack Webhook URL 추가
echo 'export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"' >> ~/.bashrc

# 변경사항 적용
source ~/.bashrc

# 확인
echo $SLACK_WEBHOOK_URL
```

### 방법 2: 임시 설정 (현재 세션만)

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

⚠️ **주의**: 임시 설정은 터미널을 닫으면 사라집니다. Cron 작업에는 방법 1 또는 Cron에 직접 설정이 필요합니다.

---

## ⏰ Cron 작업 설정

### 자동 설정 (권장)

```bash
cd /home/rlwrld/projects/scouting_program/scouting_bot

# Webhook URL이 설정되어 있는지 확인
echo $SLACK_WEBHOOK_URL

# Cron 작업 자동 설정
./setup_cron.sh
```

### 수동 설정

```bash
# Cron 편집기 열기
crontab -e

# 다음 라인 추가 (매일 오전 8시 실행)
0 8 * * * SLACK_WEBHOOK_URL='https://hooks.slack.com/services/YOUR/WEBHOOK/URL' /home/rlwrld/projects/scouting_program/scouting_bot/run_daily_crawler.sh
```

### Cron 일정 변경

시간대는 **한국시간(KST)** 기준입니다:

```bash
# 매일 오전 8시
0 8 * * *

# 매일 오전 9시 30분
30 9 * * *

# 평일 오전 8시
0 8 * * 1-5

# 주말 오전 10시
0 10 * * 0,6
```

### Cron 작업 확인

```bash
# 현재 Cron 작업 목록 보기
crontab -l

# Cron 작업 삭제
crontab -e  # 편집기에서 해당 라인 삭제
```

---

## 🧪 수동 테스트

### 1. 기본 테스트 (로그 출력)

```bash
cd /home/rlwrld/projects/scouting_program/scouting_bot

# Webhook URL 설정 (아직 안했다면)
export SLACK_WEBHOOK_URL="your-webhook-url"

# 실행
./run_daily_crawler.sh
```

### 2. Python 스크립트 직접 실행

```bash
cd /home/rlwrld/projects/scouting_program/scouting_bot

# 가상환경 활성화
source .venv/bin/activate

# Webhook URL 설정
export SLACK_WEBHOOK_URL="your-webhook-url"

# 실행
python3 daily_crawler.py
```

### 3. 로그 확인

```bash
# 오늘 로그 보기
cat logs/crawler_$(date +\%Y-\%m-\%d).log

# 최근 로그 실시간 보기
tail -f logs/crawler_$(date +\%Y-\%m-\%d).log

# 모든 로그 파일 목록
ls -lh logs/
```

---

## 🔍 문제 해결

### 문제 1: "SLACK_WEBHOOK_URL is not set" 오류

**해결책**:
```bash
# 환경 변수 확인
echo $SLACK_WEBHOOK_URL

# 없다면 설정
export SLACK_WEBHOOK_URL="your-webhook-url"

# ~/.bashrc에 영구 저장
echo 'export SLACK_WEBHOOK_URL="your-webhook-url"' >> ~/.bashrc
source ~/.bashrc
```

### 문제 2: Cron이 실행되지 않음

**해결책**:
```bash
# Cron 서비스 상태 확인
systemctl status cron

# Cron 작업 확인
crontab -l

# Cron 로그 확인
grep CRON /var/log/syslog | tail -20

# 스크립트 실행 권한 확인
ls -l /home/rlwrld/projects/scouting_program/scouting_bot/*.sh
```

### 문제 3: Python 모듈 오류

**해결책**:
```bash
cd /home/rlwrld/projects/scouting_program/scouting_bot

# 가상환경 활성화
source .venv/bin/activate

# 필요한 패키지 설치 (크롤러 의존성)
# 크롤러 실행 중 오류가 발생하면 해당 패키지 설치
pip install requests beautifulsoup4 selenium
```

### 문제 4: Slack 알림이 안 옴

**해결책**:
```bash
# Webhook URL 테스트
curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"Test message from Company Crawler"}' \
  $SLACK_WEBHOOK_URL

# 수동 실행으로 디버깅
cd /home/rlwrld/projects/scouting_program/scouting_bot
source .venv/bin/activate
export SLACK_WEBHOOK_URL="your-url"
python3 daily_crawler.py
```

### 문제 5: 시간대가 맞지 않음

**해결책**:
```bash
# 시스템 시간대 확인
timedatectl

# 한국 시간대로 설정 (이미 KST로 설정되어 있음)
sudo timedatectl set-timezone Asia/Seoul
```

---

## 📊 Slack 메시지 형식

크롤링 결과는 다음과 같은 형식으로 Slack에 전송됩니다:

```
🤖 Daily Company Crawler Report
Date: 2026-02-10 08:00:00 KST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Physical Intelligence
📝 Blog/Research: Updated
   • Added: 2 posts
      - New AI Research on Robotics
      - Building Better Manipulation Models
💼 Careers: No changes
👥 Team: No changes

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Skild AI
📝 Blog/Research: No changes
💼 Careers: Updated
   • Added: 3 positions
      - Senior ML Engineer
      - Robotics Engineer
      - Data Scientist

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔔 Summary: Updates detected! Check details above.
```

---

## 📝 추가 정보

### 로그 보관 정책

- 로그 파일은 `logs/` 디렉토리에 날짜별로 저장됩니다
- 30일 이상 된 로그는 자동으로 삭제됩니다
- 형식: `crawler_YYYY-MM-DD.log`

### 다른 프로젝트와 독립성

이 프로젝트는 다음과 같이 다른 프로젝트들과 독립적으로 실행됩니다:

1. **독립 디렉토리**: `/home/rlwrld/projects/scouting_program/scouting_bot/`
2. **독립 가상환경**: `.venv/` (프로젝트 내부)
3. **독립 Cron 작업**: 별도의 스케줄로 실행
4. **독립 로그**: `logs/` 디렉토리에 저장

### 비활성화/제거

```bash
# Cron 작업 비활성화
crontab -e  # 해당 라인 삭제 또는 주석처리 (#)

# 완전 제거
rm -rf /home/rlwrld/projects/scouting_program/scouting_bot
```

---

## ✅ 완료 체크리스트

- [ ] Slack Webhook URL 발급
- [ ] 환경 변수 설정 (`~/.bashrc`)
- [ ] Cron 작업 설정
- [ ] 수동 테스트 성공
- [ ] Slack 알림 수신 확인
- [ ] 첫 번째 자동 실행 확인 (다음날 오전 8시)

---

## 🆘 도움이 필요하신가요?

문제가 발생하면 로그 파일을 확인하세요:

```bash
# 최근 로그 보기
tail -100 logs/crawler_$(date +\%Y-\%m-\%d).log

# 에러만 필터링
grep -i error logs/crawler_$(date +\%Y-\%m-\%d).log
```

---

**설정 완료 후 매일 아침 8시에 자동으로 크롤링이 실행되고 Slack으로 알림이 옵니다! 🎉**
