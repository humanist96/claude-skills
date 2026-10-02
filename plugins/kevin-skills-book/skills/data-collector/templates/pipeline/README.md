# {{KEYWORD}} 뉴스 다이제스트 자동화

매일 정해진 시각에 뉴스 피드를 모아 기사 목록과 많이 나온 단어를 정리한 다이제스트를 만들고, 원하면 Slack으로 새 기사 제목·링크 목록을 보낸다.
data-collector 스킬이 만든 패키지다. 이 패키지는 기사를 모으고 세기만 한다. 해석과 전망은 다이제스트를 읽고 사람이나 Claude가 한다.

## 파일

| 파일 | 역할 |
|------|------|
| `run_pipeline.py` | 수집 → 집계 → 다이제스트 → 알림 순서로 실행 |
| `collector.py` | 뉴스 피드(RSS·Atom) 수집, 기간·중복 정리, NewsAPI(키가 있을 때) |
| `analyzer.py` | 단어별 언급 기사 수, 날짜·매체별 기사 수 |
| `report_generator.py` | `reports/<키워드>_<날짜>.md` 다이제스트 |
| `slack_notifier.py` | Slack 알림(웹훅 주소는 환경변수) |
| `config.yaml` | 키워드, 피드, 수집 기간, 출력 폴더 |
| `requirements.txt` | 의존성(pyyaml) |
| `.github/workflows/daily_collect.yml` | GitHub Actions 일정 실행 |
| `samples/sample_feed.xml` | 네트워크 없이 시험하는 예시 피드 |

## 1. 내 PC에서 실행

```bash
pip install -r requirements.txt
python run_pipeline.py --offline-feed samples/sample_feed.xml --no-notify   # 시험 실행(네트워크 없음)
python run_pipeline.py --no-notify                                         # 실제 수집
```

`PIPELINE RUN OK`가 나오고 `reports/` 폴더에 다이제스트가 생기면 된다.

## 2. GitHub Actions로 매일 실행

1. 이 폴더를 새 GitHub 저장소로 올린다(`.github` 폴더 포함).
2. 저장소 Settings → Secrets and variables → Actions에 `SLACK_WEBHOOK_URL`을 추가한다(알림이 필요할 때만). NewsAPI를 쓰면 `NEWSAPI_KEY`도 추가한다.
3. Actions 탭에서 워크플로를 켜고 "Run workflow"로 한 번 실행해 본다.
4. 실행 시각: {{CRON_NOTE}}. 바꾸려면 `.github/workflows/daily_collect.yml`의 cron을 고친다(UTC 기준, 한국 시각 - 9시간).

## 3. 바꿀 수 있는 것(config.yaml)

- `keywords`: 검색 키워드. 키워드마다 구글 뉴스(한국어) 피드를 자동으로 더한다
- `feeds`: 추가 RSS 피드(이름, 주소)
- `window_days`: 며칠 전 기사까지 모을지
- `max_items`: 다이제스트에 넣을 기사 수
- `slack.new_days`·`slack.max_headlines`: Slack에 보낼 새 기사 기간(일)과 개수. 매일 실행이면 1일
- 시험: `SLACK_DRY_RUN=1 python run_pipeline.py`는 Slack에 보내지 않고 메시지를 화면에 출력한다

## 주의

- Slack 웹훅 주소를 `config.yaml`에 적어 커밋하지 않는다. 저장소가 공개면 누구나 그 주소로 메시지를 보낼 수 있다.
- 피드는 언론사 정책에 따라 바뀌거나 막힐 수 있다. 수집 상태는 다이제스트 끝에 나온다.
- 다이제스트는 기사 목록이다. 투자 조언이 아니다.
