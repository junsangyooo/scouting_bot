# Scouting Bot

## 목적

경쟁 로보틱스/AI 회사들의 **채용공고(positions)** 와 **블로그/리서치(blog/research)** 를 매일 크롤링해서,
변화(신규/삭제/수정)를 감지하고 **Slack으로 자동 리포트** + **Claude AI 분석**을 보내는 경쟁사 모니터링 시스템.
추가로 Slack에서 슬래시 커맨드로 **온디맨드 분석**을 돌릴 수 있는 상시 봇이 함께 돈다.

> ⚠️ **members/team(팀 멤버) 트래킹은 제거됨.** 과거 PI 홈페이지에서 멤버 목록을 긁었으나
> 2026-04 PI가 사이트에서 멤버 섹션을 없애 크롤이 깨졌고, 전 파이프라인에서 멤버 관련 코드를 모두 제거했다.
> **어떤 곳에도 member/team 크롤·비교·표시 로직을 다시 추가하지 말 것.** (과거 `data/*/*_members.json` 스냅샷은 historical 데이터로만 보존)

## 모니터링 대상 회사

`physical_intelligence` (PI), `skild_ai`, `dyna`, `generalist_ai` — 각각 `company_crawler/<company>/` 디렉토리와 `data/<company>/` 데이터 폴더를 가진다.

## 두 개의 진입점 (둘 다 같은 데이터/크롤러를 공유)

### 1. 일일 크롤러 (cron, 매일 08:00 KST)
```
crontab: 0 8 * * * run_daily_crawler.sh
run_daily_crawler.sh → python3 daily_crawler.py
```
- `daily_crawler.py`가 각 회사의 `company_crawler/<company>/main.py:run("all")` 호출
- 크롤 → 이전 스냅샷과 비교 → 변화 있으면 Claude CLI로 분석 → Slack Block Kit 메시지 전송
- `save_daily_snapshots()`로 `data/<company>/<YYYYMMDD>_<prefix>_*.json` 스냅샷 저장
- 결과 데이터는 git에 자동 커밋/푸시됨 ("Auto-update company data ...")

### 2. 인터랙티브 Slack 봇 (상시 가동, Socket Mode)
```
setsid .venv/bin/python slack_bot.py   # PPID 1로 detached, 로그: slack_bot.log
```
- `/analyze [시작YYYYMMDD] [종료YYYYMMDD]` — 두 날짜 스냅샷을 비교 + AI 분석
- `/company_analyze` — 회사 선택 버튼 → 해당 회사 최신 JD+블로그 종합 분석
- 비교 로직은 `compare_utils.py` (`compare_positions`, `compare_blogs`, `load_snapshot`) 공유
- **재시작 방법**: 기존 프로세스 `kill` 후 위 명령으로 재기동. 코드를 고쳐도 **프로세스를 재시작해야 반영됨.**

## 회사별 크롤러 구조 (`company_crawler/<company>/`)

각 회사 폴더는 동일한 5개 파일로 구성:
- `position_crawler.py` — 채용공고 수집 → list[dict] (`id, title, location, compensation, description, description_hash, url`)
- `position_compare.py` — `data/<company>/<prefix>_positions.json`과 비교 → `{status, added, removed, updated}`
- `blog_crawler.py` — 블로그/리서치 수집
- `blog_compare.py` — 블로그 비교
- `main.py` — `run(purpose)` 진입점. `purpose ∈ {"all","blog","career"}`

`run("all")` 반환 형식:
```python
{"company": <name>, "research"|"blog": <blog_result>, "position": <position_result>}
```
> 키 네이밍 차이: `skild_ai`·`dyna`는 블로그 키가 `"blog"`, `physical_intelligence`·`generalist_ai`는 `"research"`.
> 소비측(`daily_crawler.py`, `slack_bot.py`)은 `result.get("blog") or result.get("research")`로 둘 다 처리.

## 크롤링 방식 주의점
- **PI(`physical_intelligence`)는 Playwright 기반** — pi.website가 Next.js 클라이언트 사이드 렌더링이라 `requests`로는 DOM이 안 잡힌다. 채용공고는 `section > button(아코디언) > ul > li > a[?ashby_jid=...]` 구조이며, JD 상세는 `iframe#ashby_embed_iframe` 안에 있다.
- 나머지 회사는 대체로 `requests` + BeautifulSoup. 셀렉터가 깨지면 `select_one`이 `None`을 반환하니 `None.find_all()` 류의 `AttributeError`를 조심.

## 🚨 새 회사 추가 시 반드시 함께 수정 (전체 파이프라인 동기화)

회사를 추가/제거할 때는 **아래 모든 곳을 함께** 바꿔야 일일 리포트와 인터랙티브 봇이 어긋나지 않는다:

1. **`company_crawler/<new>/`** — 기존 회사(예: `generalist_ai`) 폴더를 그대로 미러링해 5개 파일 작성. `__init__.py`가 있으면 함께.
2. **`daily_crawler.py`**:
   - 상단 `from <new>.main import run as run_<new>` import 추가
   - `COMPANIES` 딕셔너리에 `"<new>": ("<Display Name>", run_<new>, "<prefix>")` 추가
   - `DATA_FILES` 딕셔너리에 `data/<new>/<prefix>_positions.json`, `<prefix>_blog.json` 추가
3. **`slack_bot.py`** — `COMPANIES` 딕셔너리에 `{"name", "prefix", "data_dir", "files": ["positions","blog"]}` 추가 (`/analyze`·`/company_analyze` 버튼이 자동 생성됨). **수정 후 봇 재시작 필수.**
4. (선택) `company_crawler/main.py` — 레거시 대화형 CLI. 쓰면 `COMPANIES`에 추가.

> 핵심: **크롤러 추가만 하고 `slack_bot.py`를 빠뜨리면** 일일 리포트엔 나오지만 슬랙 봇 명령에는 안 보인다. 항상 양쪽 `COMPANIES`를 같이 갱신할 것.

## 환경 / 실행
- Python venv: `.venv` (`slack_bolt`, `playwright`, `beautifulsoup4`, `python-dotenv`, `slack_sdk` 등 설치됨)
- `.env` 필요 키: `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`(Socket Mode용), `SLACK_SIGNING_SECRET`, `SLACK_CHANNEL_ID`
- AI 분석은 `claude` CLI를 `subprocess`로 호출 (`claude -p --model sonnet`)
- 일일 크롤러 로컬 테스트(슬랙 전송 스킵): `TEST_MODE=true .venv/bin/python daily_crawler.py`
- 데이터(`data/`)는 git으로 추적됨 (변경 이력 = 일별 스냅샷)
