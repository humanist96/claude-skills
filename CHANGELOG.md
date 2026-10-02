# 변경 이력

이 문서는 플러그인 사용자에게 영향을 주는 변경을 기록한다. 버전은 semver를 따른다(스킬 동작 변경은 minor, 이름·입출력 변경은 major).

## 2.0.0-alpha.1 — Phase 1: doc-automation·excel-automation·meeting-minutes·content-repurpose·data-collector·content-research·generate-shorts 고도화, hwpx-editor 분리 (v2 브랜치, 미배포)

### generate-shorts (재설계)
- 입력: 로컬 영상 + 자막(권장), 로컬 영상 + 음성 인식(faster-whisper 선택), 권리를 확인한 YouTube URL(`--i-have-rights`). 세 입력 모두 `prepare_source.py`가 같은 대본 파일로 만든다
- 정책(D8): 브라우저 쿠키 자동 사용, User-Agent 위장, 무작위 지연, '봇 감지 우회' 안내를 삭제했다. 쿠키는 사용자가 환경변수로 설정할 때만 쓴다. 권리 확인 없는 URL은 받지 않는다
- Windows: 공유 `media.py`(ffmpeg를 PATH·환경변수·imageio-ffmpeg 순으로 찾고 ffprobe 없이 정보 읽기, 필터 경로 이스케이프), 맑은 고딕, `python3` 대신 현재 파이썬, CRLF 자막
- 검증: `validate_highlights.py`(길이·범위·겹침·자막 시간·제목/후크 길이·문장 경계), `verify_short.py`(해상도·길이·오디오·검은 화면·오버레이 실패)
- 평가에서 찾아 고친 것: 자막·후크 합성 실패를 성공으로 숨기던 동작, Windows 두 줄 후크의 빈 줄, 카드 제목 한글 획 뭉개짐, 제목 전체를 붙인 해시태그, 메모리 부족 시 음성 인식 중단(작은 모델로 다시 시도)
- 삭제: `setup.sh`(brew·apt 전용), `reference.md`(references 4개로 나눔), 제3자 방송 자막 결과물
- 평가: v1.6.1 대비 기대 항목 통과율 0.95 → 1.00(4개 eval). v1.6.1은 쇼츠·카드를 만든 3번 모두 에이전트가 어댑터 코드를 직접 짰다. 상세 `docs/03-analysis/generate-shorts-phase1.analysis.md`

### content-research (재설계, data-collector와 엔진 통합)
- 역할: 콘텐츠 기획 전용(유튜브·블로그·뉴스레터·SNS 주제, 발행 캘린더). 시장 리서치 보고서는 data-collector
- 워크플로: 범위(기본값 1회 확인) → 수집(`feeds.py`, 구글 뉴스 한국어 포함, 받은 피드 파일만으로도) → 정리(공유 엔진 `prepare_sources.py`, RSS 파일 직접) → 기획(주제마다 근거 번호·'왜 지금') → 캘린더(`calendar_slots.py`) → 검증(`verify_plan.py`)
- 삭제: 세션 안 Anthropic API 재호출과 API 키 `.env`, 가상환경·feedparser 설치, 질문 4개 필수, 날짜 박힌 모델 ID
- 검증: 근거 없는 주제, 기간 밖 근거, 숫자 출처, 예상 조회수 같은 성과 수치, 루머 표시, 중복 주제, 개수, 용도별 필수 요소, 캘린더 날짜·요일, 지시문·할인 코드
- 공유 엔진: `shared/optional`의 prepare_sources·numparse·source-tiers를 data-collector와 함께 쓴다. 영어 단어 뒤 숫자·영어 퍼센트 인식을 고쳤다(data-collector에도 적용)
- 평가: v1.6.1 대비 기대 항목 통과율 0.946 → 0.977(4개 eval, 차이 작음). v1.6.1은 API 키 없이 핵심 분석 단계가 동작하지 않았다. 상세 `docs/03-analysis/content-research-phase1.analysis.md`

### data-collector (재설계)
- 워크플로: 범위(기본값 1회 확인) → 리서치 플랜(`profiles.py`) → 수집(WebSearch·WebFetch 또는 받은 자료) → 정리(`prepare_sources.py`) → 통계(`trend_stats.py`) → 교차 검증 → 출처 각주 보고서 → 검증(`verify_report.py`)
- 정리: S번호, URL·사본 중복, 기간 밖, 날짜 없음, 신뢰 등급(A 공식~D 보도자료·블로그), 자료 속 지시문 표시(따르지 않음)
- 검증: 출처 없는 숫자, 인용 소스에 없는 숫자, 기간 밖 자료를 현재처럼, 출처 목록·URL, 투자 권유, 면책, 근거 없는 논조 비율, 지시문 반영, 자리표시
- 삭제: 단어 사전 센티먼트(긍정·부정 %), 자리표시뿐인 보고서 생성기, 컨테이너 전용 경로, 질문 3개 필수, API 키를 적는 config.yaml
- 자동화 패키지: 템플릿 복사 + 검사 + 예시 피드 시험 실행. 한국어 구글 뉴스(기간 제한), Slack 새 기사 목록, `SLACK_DRY_RUN`, 커밋 권한
- 도메인 프로필: 한국어 뉴스 피드 추가, 응답하지 않는 피드 6개 정리, 검색어의 고정 연도 제거
- 오버라이드: 기본 분야·깊이·기간·언어, 신뢰 소스 등급, 면책 문구, 보고서 구조, 추가 도메인 프로필
- 평가: v1.6.1 대비 기대 항목 통과율 0.805 → 1.00(4개 eval). 상세 `docs/03-analysis/data-collector-phase1.analysis.md`

### 이름 변경 (호환성 깨짐)
- 마켓플레이스 `claude-skills` → `kevin-claude-skills`, 플러그인 `claude-skills-book`·`-creator`·`-practice` → `kevin-skills-book`·`-creator`·`-practice`(폴더 `plugins/kevin-skills-*`). 최신 Claude Code CLI가 `claude-`로 시작하는 플러그인 이름을 예약어로 거부하고, 이름에 `claude-skills`가 들어가면 Anthropic 공식 플러그인처럼 읽힌다고 경고한다. 설치 명령: `/plugin install kevin-skills-book@kevin-claude-skills`. 슬래시 호출도 `/kevin-skills-book:<스킬>`로 바뀐다. 오버라이드 폴더 `.claude/claude-skills/`는 그대로다

### content-repurpose (재설계)
- 워크플로: 원본 정리(`brief.json`: 핵심 메시지·숫자·단서) → 플랫폼 정하기(요청 → 맞춤 기본값 → 한 번 확인, 못 물으면 블로그·X·인스타) → 선택한 플랫폼 스펙만 읽고 작성 → `check_repurpose.py` → 저장·전달
- 검사: 플랫폼별 실제 한도(X 가중치 280, 인스타 2,200자·해시태그 30개 등)와 권장 분량 구분(`count_chars.py`), 원본에 없는 숫자, 빠진 플랫폼·필수 요소, 자리표시·작성 메모·코드 블록·안내문, 핵심 메시지 누락
- 감사·갭: `content_inventory.py`가 카테고리 분포·편중, 마지막 발행 후 경과, 시의성 제목, 중복 후보, 경쟁 비교를 집계
- 삭제: "외부 파일을 찾지 마라" 지시, Cowork 저장 경로·링크 형식 고정, 질문 필수 규칙
- 예시: v1.6.1 예시에 섞여 있던 원본에 없는 숫자(수수료 30%·0%, 2시간·4시간)와 틀린 계산식을 걷어내고 검증을 통과하는 예시로 교체
- 오버라이드: 기본 플랫폼·톤·언어, 브랜드 보이스, 금지어, 사내 플랫폼 스펙 추가
- 평가: v1.6.1 대비 기대 항목 통과율 1.00 대 1.00(6개 eval, iteration-2). 차이를 측정하지 못했다(천장 효과, handoff H12). 상세 `docs/03-analysis/content-repurpose-phase1.analysis.md`

### meeting-minutes (재설계)
- 워크플로: 용도 정하기(요청 → 맞춤 기본값, 필요할 때만 한 번 확인) → 번호 붙은 녹취(음성 `transcribe.py`, 텍스트 `prepare_transcript.py`) → `minutes.json`(결정·할 일·미결에 근거 발언 번호) → `verify_minutes.py` → `build_minutes.py`(용도 4 × 형식 4)
- 검증: 근거 번호, 담당자·참석자·기한·숫자를 녹취와 대조, STT 교정은 선언하고 근거 확인, 렌더링 누락·홍보 문구 검사
- STT: 모델 자동 선택(한국어 small), 크기 제한 없음·이어하기, 확신 낮은 발언 표시. 용어 사전은 교정 참고(인식 힌트는 `--hotwords` 선택)
- 텍스트 입력: 클로바노트·SRT·VTT·워드·화자 표기 자동 감지
- 삭제: claude.ai 컨테이너 경로 가정, '질문 3개 필수', 결과 끝 홍보 문구
- 평가: v1.6.1 대비 기대 항목 통과율 0.975 대 0.977(4개 eval, iteration-2). 사실상 동률이며, v1.6.1은 음성 실행 6번 모두 STT 오류를 에이전트가 우회해야 했다. 상세 `docs/03-analysis/meeting-minutes-phase1.analysis.md`

### 수정
- faster-whisper 1.2.1 + PyAV 15 이상에서 mp3 변환이 `metadata_errors` 오류로 실패하던 문제(직접 디코딩)

### excel-automation (재설계)
- 워크플로: 구조 파악(`excel_profile.py`) → 기능 판단 → 결정적 엔진(정리 `clean_data.py`, 분석 `analysis_tools.py`, 취합 `consolidate.py`) → 재계산(`recalc.py`, Excel·LibreOffice) → 품질 게이트(`verify_excel.py`)
- 정리 원칙: 완전 중복만 삭제, 안전한 전화번호·날짜만 통일, 오타·극단값·모호한 날짜·유사 중복·빈 칸은 고치지 않고 후보 시트로 보고, 모든 셀 변경을 기록
- 분석: 엑셀 기본 차트, 히트맵 서식, 숫자마다 근거 셀이 붙은 인사이트 시트
- 취합: 모든 탭 키의 합집합, IFERROR(INDEX/MATCH) 수식, 원본 탭 보존, 취합리포트. XLOOKUP·FILTER 등 금지
- 오버라이드: 날짜 순서, 극단값 기준, 유사 중복 키, 취합 빈 칸 표시, 범주 표기 사전, 회사 데이터 규칙
- 평가: v1.6.1 대비 기대 항목 통과율 0.93 → 1.00(3개 eval), 실행 시간 245초 → 148초. 상세 `docs/03-analysis/excel-automation-phase1.analysis.md`

### 실습 샘플
- 9장 쇼츠 실습: 제3자 방송 영상의 자동자막 결과물 대신 자체 제작 강의 영상(`shorts-lecture`, 106초, 자막 포함)과 정답표(`shorts-answer-key`)를 넣었다. 정보 구간 3개와 인사·잡담·마무리 구간 3개를 일부러 섞었다.
- 7장 콘텐츠 리서치 실습: 가상 테크 뉴스 RSS 12건(`research-feed`)과 정답표(`research-answer-key`)를 추가했다. 중복·기간 밖 기사, 루머, 지시문, 할인 코드, 3개월 캘린더 정답을 넣었다.
- 6장 리서치 실습: 가상 기사 13건(`collector-articles`)과 정답표(`collector-answer-key`)를 추가했다. 중복·기간 밖·날짜 없는 기사, 상충 수치, 지시문, IR을 일부러 넣었다.
- 8장 리퍼포징 실습: 제3자 유튜브 녹취 대신 자체 작성 원본 대본(`repurpose-source`)과 정답표(`repurpose-answer-key`, 책 8-1·8-2 집계 정답 포함)를 추가했다.
- 4장 회의록 실습: 클로바노트 형식 녹취록(`meeting-text`)과 녹음 3개·녹취록 정답표(`meeting-answer-key`)를 추가했다.
- 3장 엑셀 실습: 진짜 원본 3종(`inputs/*_원본.xlsx`)과 강사용 정답표를 추가했다. v1.6.1에서 실습 입력으로 배포되던 파일은 이미 처리된 결과물이라 완성 예시 세트로 옮겼다.
- `excel-automation/prompt/2.md`(빈 파일)를 스킬 사용 실습 프롬프트로 채웠다.

### doc-automation (재설계)
- 워크플로: 보고 맥락 → 출처 ID 추출(`extract_sources.py`) → 전문 정독 → 스토리라인(`outline.json`) → 렌더링(`build_deck.py`) → 품질 게이트(`verify_deck.py`, `render_slides.py`) → 보고 메일
- 9종 슬라이드, 편집 가능한 네이티브 차트·표, 회사 템플릿의 크기·레이아웃·제목 칸 사용, 한글 단어 단위 줄바꿈(lang=ko-KR)
- 숫자 출처 검증: 본문·표·차트의 모든 숫자를 출처와 대조. 계산값은 outline `derived`에 계산식 선언
- 오버라이드: 회사 템플릿, 기본 보고 대상·장수·글꼴·강조색, 이메일 양식, 회사 보고서 규칙
- 평가: v1.6.1 대비 기대 항목 통과율 0.79 → 1.00(4개 eval). 상세 `docs/03-analysis/doc-automation-phase1.analysis.md`

### hwpx-editor (신규, doc-automation에서 분리)
- 텍스트 노드 안에서만 치환, 새 글자 XML 이스케이프, plan(사전 확인)·strict 실행, verify_hwpx(양식 보존 검증), 탐색기 미리보기 텍스트 갱신, 배포용(암호화) 문서 안내
- 책 2장 API(`replace_texts`, `fill_template`, `extract_texts`, `scan_placeholders`) 유지

### 수정
- template_analyzer·create_pptx의 플레이스홀더 번호표 오류(회사 템플릿 제목 칸을 찾지 못함)
- 빠른 주간보고 모드가 같은 기간 앞·뒤 비교를 "전주 대비"로 표기하던 문제
- 배포용(암호화) HWPX를 ParseError 대신 안내 문구로 처리

### 변경(호환성)
- `generate_report.py --hwpx-template` 제거 → hwpx-editor의 `fill` 사용

## 2.0.0-alpha.0 — Phase 0 공통 기반 (v2 브랜치, 미배포)

### 구조 변경 (major)
- 단일 플러그인을 3개로 분리했다.
  - `kevin-skills-book`(업무): doc-automation, excel-automation, meeting-minutes, data-collector
  - `kevin-skills-creator`(콘텐츠·영상): content-research, content-repurpose, generate-shorts, narration-video
  - `kevin-skills-practice`(실습): practice-samples, doctor (신규)
- 실습 샘플과 예시 결과물을 업무·크리에이터 플러그인에서 빼고 `practice-samples` 스킬로 옮겼다. 업무 플러그인 설치 크기는 약 20MB에서 0.4MB가 됐다.
- 마켓플레이스 소유자를 humanist96으로 정리했다.

### 추가
- `doctor`: Python·패키지·ffmpeg·yt-dlp·uv·LibreOffice·한글 폰트·쓰기 권한·디스크·(선택) 네트워크를 점검하고 OS별 해결 명령을 알려 준다.
- `practice-samples`: 장·스킬별 샘플 세트를 작업 폴더로 복사한다. 이미 있는 파일은 덮어쓰지 않는다.
- 공통 모듈(`shared/` → 각 스킬 `scripts/_vendor/`, `references/_shared/`): 실행 환경 감지, 한글 폰트 탐색(Windows 포함), 출력 경로, 사용자 맞춤(오버라이드) 탐색·검사.
- 사용자 맞춤 규약: `.claude/claude-skills/<스킬명>/` 오버라이드 폴더, 보호 규칙 5개.
- 의존성 고정: 모든 requirements를 `==`로 고정(yt-dlp는 예외, 사유 기록), 루트 `constraints.txt`. meeting-minutes·generate-shorts에 requirements.txt 신설.
- 검증 도구와 CI: 정적 스킬 검증(baseline 방식), vendoring 동기화, 단위 테스트, eval 골격(스킬별 smoke 1건), `claude plugin validate --strict`, 깨끗한 가상환경 재현 설치.

### 수정
- 예제 docx 6개(+책 챕터 사본)에 내장된 Google Sans 글꼴(각 2.9MB)을 제거했다. 본문 텍스트는 원본과 같다.
- 셸 스크립트 줄바꿈을 LF로 고정했다(`.gitattributes`). Windows에서 CRLF로 체크아웃되면 bash가 실패하던 문제.
- requirements 파일을 ASCII로만 작성한다. 한국어 Windows의 pip는 cp949로 읽어 한글 주석이 있으면 설치가 실패한다.

### 제거
- 작성자 로컬 경로가 하드코딩된 1회성 스크립트 4개(`fix_docx.py`, `fix_docx_round2.py`, `fix_captions.py`, `make_fireworks_report.py`).
- 개발 도구 상태 파일(`docs/.pdca-*`, `docs/.bkit-memory.json`).

### 알려진 제약
- `claude plugin eval` 케이스는 문서화된 형식으로 작성했지만, 이 계정에서 해당 기능이 early access라 실제 실행 검증은 하지 못했다.
- 스킬 본문의 환경 전용 경로(31건) 등은 baseline으로 동결했고 Phase 1에서 스킬별로 해소한다.

## 1.6.1

책 출간 시점 구성. `v1.6.1` 태그 참고.
