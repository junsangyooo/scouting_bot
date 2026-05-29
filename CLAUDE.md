# Scouting Bot

## 목적

경쟁 로보틱스/AI 회사들의 **채용공고(positions)** 와 **블로그/리서치(blog/research)** 를 매일 크롤링해서,
변화(신규/삭제/수정)를 감지하고 **Slack으로 자동 리포트** + **Claude AI 분석**을 보내는 경쟁사 모니터링 시스템.
추가로 Slack에서 슬래시 커맨드로 **온디맨드 분석**을 돌릴 수 있는 상시 봇이 함께 돈다.

> ⚠️ **members/team(팀 멤버) 트래킹은 제거됨.** 과거 PI 홈페이지에서 멤버 목록을 긁었으나
> 2026-04 PI가 사이트에서 멤버 섹션을 없애 크롤이 깨졌고, 전 파이프라인에서 멤버 관련 코드를 모두 제거했다.
> **어떤 곳에도 member/team 크롤·비교·표시 로직을 다시 추가하지 말 것.** (과거 `data/*/*_members.json` 스냅샷은 historical 데이터로만 보존)

## 모니터링 대상 회사

`physical_intelligence` (PI), `skild_ai`, `dyna`, `generalist_ai`, `sunday` (Sunday Robotics), `genesis` (Genesis AI), `rhoda` (Rhoda AI) — 각각 `company_crawler/<company>/` 디렉토리와 `data/<company>/` 데이터 폴더를 가진다.

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
- `/analyze [시작YYYYMMDD] [종료YYYYMMDD]` — 두 날짜 스냅샷을 비교 + AI 분석 (양 끝점만 비교)
- `/company_analyze <회사> [시작YYYYMMDD] [종료YYYYMMDD]` — **온디맨드 단일 회사 분석 에이전트**.
  날짜 생략 시 그 회사 전체 보유 기간. 인자 없이 호출하면 회사 선택 버튼(클릭=전체 기간).
  내부적으로 `analysis_engine.py`가 **범위 내 모든 스냅샷을 연속쌍으로 walk**해(중간에 열렸다 닫힌 공고까지 포착)
  채용 추이·속도·직무/시니어리티 믹스·지역·공고수명·블로그 cadence/테마를 **결정론적으로 계산** → Block Kit 카드,
  그 요약을 claude CLI에 넘겨 AI 해설을 덧붙임. 회사 토큰은 prefix/별칭 fuzzy 매칭(`resolve_company`).
- 분석 엔진 `analysis_engine.py`는 Slack/env 비의존 — `.venv/bin/python analysis_engine.py <회사> [시작] [종료]`로 단독 검증 가능.
- 비교 로직은 `compare_utils.py` (`compare_positions`, `compare_blogs`, `load_snapshot`) 공유. `analysis_engine`도 이를 재활용.
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
> 키 네이밍 차이: `skild_ai`·`dyna`·`genesis`는 블로그 키가 `"blog"`, `physical_intelligence`·`generalist_ai`·`sunday`·`rhoda`는 `"research"`.
> 소비측(`daily_crawler.py`, `slack_bot.py`)은 `result.get("blog") or result.get("research")`로 둘 다 처리.

## 크롤링 방식 주의점
- 🛡️ **빈-크롤 가드 (모든 `position_compare`/`blog_compare`에 필수)**: 크롤이 `[]`(0건)를 반환했는데 이전 스냅샷에 데이터가 있으면 = **거의 항상 크롤러가 깨진 것**(셀렉터/사이트 변경·네트워크). 이때 `if not curr and prev: return {"status":"checked"}` 로 **저장을 건너뛰고** 종료한다 — 안 그러면 좋은 데이터를 `[]`로 덮어쓰고 "전량 삭제 -100%" 가짜 리포트를 쏜다(2026-05-29 genesis 사고가 정확히 이것). **새 회사 추가 시 이 가드를 반드시 미러링할 것.** 가드는 *빈 크롤*만 막는다(정상적인 대량 변동은 통과).
- **PI(`physical_intelligence`)는 Playwright 기반** — pi.website가 Next.js 클라이언트 사이드 렌더링이라 `requests`로는 DOM이 안 잡힌다. 채용공고는 `section > button(아코디언) > ul > li > a[?ashby_jid=...]` 구조이며, JD 상세는 `iframe#ashby_embed_iframe` 안에 있다.
- 나머지 회사는 대체로 `requests` + BeautifulSoup. 셀렉터가 깨지면 `select_one`이 `None`을 반환하니 `None.find_all()` 류의 `AttributeError`를 조심.
- **`dyna`(DYNA)는 Playwright 기반** — dyna.co가 Lovable SPA로 리빌드됨(2026-04 경). 리서치/회사 글이 `/research`+`/blog` 두 페이지에 **동일 카드 마크업**으로 흩어져 있어 둘을 **하나의 "blog" 스트림**으로 합쳐 추적. 카드 = `div.group.cursor-pointer`(제목 `h2`/`h3`, 발췌 `p.hidden.md:block`, 날짜 `span` "MMM 'YY" 월·연도만). **카드가 `<a>`가 아니라 라우터 기반이라 per-post URL이 없어** `url`은 listing 페이지를 가리킨다. id = `md5(title+date)`. (구 `div.flex.flex-col.mb-16` 셀렉터는 리디자인으로 죽어 ~7주간 `[]`만 반환했었음.)
- **`genesis`(Genesis AI)도 Playwright 기반** (genesis.ai는 SvelteKit CSR).
  - 채용: `genesis.ai/careers`에서 `a[href*="jobs.ashbyhq.com/genesis-ai/"]` 링크(제목/부서/위치/근무형태 inline) 수집 → 각 **Ashby** 상세 페이지에서 JD/보상 추출 (DYNA·Sunday와 동일 Ashby 구조). id는 Ashby UUID 사용. (`jobs.ashbyhq.com/genesis-ai` 보드 자체는 링크 구조가 달라 안 쓰고, careers 페이지를 출발점으로 삼는다.) ⚠️ **CSR이라 링크가 JS 렌더 후에야 뜬다 — 고정 sleep은 racy**(느린 렌더 시 0건 반환 → 위 가드가 막지만 데이터가 stale해짐). `page.wait_for_selector('a[href*="...genesis-ai/"]')`로 링크가 실제로 뜰 때까지 대기할 것.
  - 블로그: `/blog`(research) + `/press`(news)를 **하나의 "blog" 스트림**으로 합쳐 추적. 카드 = `a.container.debug-grid-item`(라인 = `[date, category, title]`), 상세 본문 = `section.article-block` 안의 `p.description` + `.blocks`. 각 글 상세에 재귀 진입해 `content` 전문까지 저장하고 `content_hash`로 변경 감지(Sunday와 동일 스키마).
- **`rhoda`(Rhoda AI)도 Playwright 기반** (rhoda.ai는 정적 HTML이지만 채용이 Ashby 임베드라 Playwright 사용).
  - 채용: `rhoda.ai/careers`는 `iframe#ashby_embed_iframe`(src=`jobs.ashbyhq.com/rhoda-ai?embed=js`)로 Ashby 보드만 임베드 → 그래서 보드 `jobs.ashbyhq.com/rhoda-ai`를 **직접** 크롤한다 (DYNA·Sunday와 동일 Ashby 구조). 목록 `a[href$=/rhoda-ai/<UUID>]`의 `h3`(제목)+`p`("부서 • 위치 • Full time • [On-site]") 수집 → 각 Ashby 상세에서 JD/보상. id는 Ashby UUID(genesis와 동일).
  - 리서치(블로그 키 `"research"`): 현재 **News만**(`rhoda.ai/news`) 추적 — 리서치는 별도 listing이 없어 추후 `blog_crawler.LIST_PAGES`에 `("research", …)`만 추가하면 합쳐진다. 카드 = `div.news-card`(`span.badge-source`/`h3>a`/`span.news-date`/`p.news-excerpt`). 내부 글(`/news/<slug>`)은 상세(`.press-card`/`.press-copy`/`#about`)에 재귀 진입해 `content`+`content_hash` 저장, **외부 기사(Bloomberg 등)는 본문 크롤 불가 → 제목/날짜/출처만** 추적(content 빈 값).

## 🚨 새 회사 추가 시 반드시 함께 수정 (전체 파이프라인 동기화)

회사를 추가/제거할 때는 **아래 모든 곳을 함께** 바꿔야 일일 리포트와 인터랙티브 봇이 어긋나지 않는다:

1. **`company_crawler/<new>/`** — 기존 회사(예: `generalist_ai`) 폴더를 그대로 미러링해 5개 파일 작성. `__init__.py`가 있으면 함께.
2. **`daily_crawler.py`**:
   - 상단 `from <new>.main import run as run_<new>` import 추가
   - `COMPANIES` 딕셔너리에 `"<new>": ("<Display Name>", run_<new>, "<prefix>")` 추가
   - `DATA_FILES` 딕셔너리에 `data/<new>/<prefix>_positions.json`, `<prefix>_blog.json` 추가
   - `COMPANY_LINKS` 딕셔너리에 `"<Display Name>": {"career": <url>, "blog": <url>}` 추가 (리포트의 Blog/Career 라벨 하이퍼링크용 — display name 기준).
3. **`slack_bot.py`** — `COMPANIES` 딕셔너리에 `{"name", "prefix", "data_dir", "files": ["positions","blog"], "career_url", "blog_url"}` 추가 (`/analyze`·`/company_analyze` 버튼이 자동 생성되고 summary 라벨 링크에 쓰임). **수정 후 봇 재시작 필수.**
4. **`analysis_engine.py`** — 상단 `COMPANIES`(name/prefix/data_dir)와 `ALIASES`(prefix/별칭→key)에 추가. 빠뜨리면 단독 CLI와 `resolve_company` 매칭이 어긋난다.

> 핵심: **크롤러 추가만 하고 `slack_bot.py`/`analysis_engine.py`를 빠뜨리면** 일일 리포트엔 나오지만 슬랙 봇 명령에는 안 보인다. 세 곳 `COMPANIES`(daily_crawler·slack_bot·analysis_engine)를 항상 같이 갱신할 것.

## 환경 / 실행
- Python venv: `.venv` (`slack_bolt`, `playwright`, `beautifulsoup4`, `python-dotenv`, `slack_sdk` 등 설치됨)
- `.env` 필요 키: `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`(Socket Mode용), `SLACK_SIGNING_SECRET`, `SLACK_CHANNEL_ID`
- AI 분석은 `claude` CLI를 `subprocess`로 호출 (`claude -p --model sonnet`)
- 일일 크롤러 로컬 테스트(슬랙 전송 스킵): `TEST_MODE=true .venv/bin/python daily_crawler.py`
- 데이터(`data/`)는 git으로 추적됨 (변경 이력 = 일별 스냅샷)

## 운영
- **크론**: `0 8 * * * run_daily_crawler.sh` (이미 등록됨). 셸 스크립트가 venv 활성화 → `daily_crawler.py` 실행 → `data/`에 변경 있으면 자동 `git add -A data/ && commit && push origin main`까지 한다.
- **로그**: 일일 크롤은 `logs/crawler_YYYY-MM-DD.log`(30일 보관, 셸이 자동 정리), 슬랙 봇은 루트 `slack_bot.log`. `logs/analysis/`에 회사별 AI 분석 결과 txt 보관.
- **AI 인사이트는 포지션 변화에만 붙는다** — `daily_crawler.crawl_all_companies()`가 `position.status == "updated"`일 때만 `analyze_position_changes`를 호출한다. 블로그 신규 글은 리포트에 목록으로만 나가고 AI 해설은 안 붙는다.
- **일일 리포트는 "회사별 변화목록 루트 메시지 + AI Analysis 쓰레드 답글" 구조** (`daily_crawler.send_slack_notification`):
  - **루트 메시지**(`format_slack_message`): 헤더 + 날짜 + **회사별 Blog/Career 변화 목록**(`- *Blog:* Checked` 또는 `- *Blog:*` + Added/Removed/Updated 항목, 제목=링크). `Blog:`/`Career:` 라벨은 각 회사 블로그·리서치/채용 페이지 하이퍼링크(`_label`). 즉 **블로그/뉴스 추가는 루트 메시지에 그대로 보인다.**
  - **쓰레드 답글**(`build_analysis_thread_blocks`, 회사당 1개, **AI 분석이 있을 때만** = career 변화 시): Block Kit `[header] 📊 {기업명} · AI Analysis` → 분석 본문 → `🔗 채용 페이지 보기`. AI 분석은 포지션 변화에만 생성되므로 blog만 바뀐 회사는 쓰레드 답글이 없다(변화는 루트에 있음). webhook 폴백은 쓰레드 불가라 개별 메시지로 보낸다.
  - 페이지 링크 출처: daily_crawler `COMPANY_LINKS`(display name 기준), slack_bot `COMPANIES[*].career_url/blog_url`. 새 회사 추가 시 두 곳 모두 채울 것. **이 구조는 `daily_crawler.py`만 고치므로 슬랙 봇 재시작과 무관**(봇 재시작은 `slack_bot.py` 변경 시에만).
  - 인터랙티브 봇은 별도 UX: `/analyze`는 summary, `/company_analyze`는 metric 카드 메시지 아래 쓰레드로 AI 해설을 붙인다.
  - 모든 Slack 전송(`chat_postMessage`/webhook)은 `unfurl_links=False, unfurl_media=False`로 **링크 미리보기(unfurl)를 끈다** — 링크가 많은 리포트에서 미리보기 카드가 주렁주렁 달리는 걸 방지. 새 전송 코드 추가 시에도 이 두 옵션을 넣을 것.
