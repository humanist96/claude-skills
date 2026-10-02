# Gates: Phase 1 — content-research 고도화와 data-collector 통합(D1) (계획서 §1.2(4), §4 Phase 1 순서 5, §5 D1)

OWNS: plugins/kevin-skills-creator/skills/content-research/**, plugins/kevin-skills-book/skills/data-collector/**, shared/optional/**, plugins/kevin-skills-practice/skills/practice-samples/samples/content-research/**, plugins/kevin-skills-practice/skills/practice-samples/samples/catalog.json, tools/**, tests/**, .github/workflows/ci.yml, docs/**, CHANGELOG.md, README.md, GATES.p1-content-research.md, .workspace/**

Scope: content-research를 "콘텐츠 기획"(주제 아이디어·훅·용도별 형식·캘린더) 전용 스킬로 재설계하고, 수집 자료 정리와 숫자 출처 엔진(prepare_sources·numparse·신뢰 등급)을 data-collector와 공유 모듈로 합친다(D1 권장안). Anthropic API 재호출·API 키·가상환경 설치 절차를 없애고, 국내 소스와 RSS 파일 입력을 지원하며, 실습 피드와 정답표를 갖추고 v1.6.1 대비 평가 결과를 증거로 남긴다. 책 7장의 `/content-research <분야>` 호출과 용도별 결과(유튜브·블로그·뉴스레터·3개월 캘린더)는 유지한다.

- [x] R0: this ledger states outcomes that can fail
  CHECK: node C:/Users/Admin/.claude/skills/unlazy/scripts/gate-lint.mjs GATES.p1-content-research.md
  EXPECT: LINT OK
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T06:00:20.130Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=dfd6fe455c2a591c6917cdee9c62f6b6a1719f07db1c9856e43b80bd35c8bcb2; output-bytes=394

- [x] R1: 공유 엔진(prepare_sources·numparse·source-tiers)이 shared/optional 한 곳에만 있고 두 스킬의 _vendor 사본이 원본과 같으며, data-collector의 기존 검증 전체가 공유 엔진으로 통과한다
  CHECK: python tests/check_shared_research_engine.py
  EXPECT: SHARED ENGINE OK
  DEPS: tests/check_shared_research_engine.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T06:00:32.557Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=dc1d22fc73903f51c91faa473d86243c8374e691a77ec880a57d077a0846ac31; output-bytes=1583

- [x] R2: 실습 피드(자체 작성 가상 기사 RSS)와 정답표가 재현 가능하게 생성되고, 정답표의 기간 밖·중복·루머·지시문·홍보 코드가 피드 내용과 일치한다
  CHECK: python tests/check_research_practice.py
  EXPECT: RESEARCH PRACTICE OK
  DEPS: tests/check_research_practice.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T06:00:33.370Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=4846c53765886294e04f06ebc79f634e63ec867825383f6a4c26fc8ec6902ded; output-bytes=811

- [x] R3: prepare_sources가 RSS·Atom 파일을 읽어 정답표대로 정리한다(중복·기간 밖·등급·지시문)
  CHECK: python tests/check_prepare_sources.py
  EXPECT: PREPARE SOURCES OK
  DEPS: tests/check_prepare_sources.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T06:00:35.494Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=00ddda8be74e0ef7a2bab75cd39a52957b5b67fa85bf2cfe3e72e1dbbd698946; output-bytes=971

- [x] R4: calendar.py가 시작일·주 수·요일·주당 횟수로 발행 일정을 정확히 만들고(지난 날짜·요일 오류 없음) 잘못된 입력을 거부한다
  CHECK: python tests/check_research_calendar.py
  EXPECT: RESEARCH CALENDAR OK
  DEPS: tests/check_research_calendar.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T06:00:37.577Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=5a1b9adcd760a6ffdcc17c14a21da1c3fd6c51277bac94efd4a6860cc2892e5a; output-bytes=481

- [x] R5: verify_plan.py가 출처 없는 아이디어·없는 소스 번호·제외 소스만 근거·인용 소스에 없는 숫자·근거 없는 성과 수치·루머 미표시·중복 아이디어·요청 개수 불일치·용도별 필수 요소 누락·캘린더 날짜 오류·지시문 반영·자리표시를 각각 잡고, 기준 기획안은 통과시킨다(양성 대조)
  CHECK: python tests/check_plan_verify.py
  EXPECT: PLAN VERIFY CONTROL OK
  DEPS: tests/check_plan_verify.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T06:00:47.380Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=b750ac35679bfc4be4a6ca3e398981be05d36f9e5086747c27ec46d8221ae5a2; output-bytes=1165

- [x] R6: content-research SKILL.md·README가 품질 규약을 충족하고 data-collector도 계속 충족한다
  CHECK: python tools/check_skill_quality.py content-research data-collector
  EXPECT: SKILL QUALITY OK
  DEPS: tools/check_skill_quality.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T06:00:47.904Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=dc391baa785c87217c0652a5ffe8ff98c3e7736262308b8e1f1239b94b69b3bb; output-bytes=61

- [x] R7: 회귀 없음 — Phase 0·앞선 Phase 1 스킬 검증 전체가 통과한다
  CHECK: python tools/run_regression.py
  EXPECT: REGRESSION OK
  DEPS: tools/run_regression.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T06:05:58.923Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=8469c0efb8d9f3ab44401cc48b40a94e04a780089e49a165e7f7a278a1550c50; output-bytes=1865

- [x] R8: skill-creator 형식 evals.json이 유튜브 주제·뉴스레터·3개월 캘린더·실시간 웹 기획을 다루고 책 7장 요청 문구를 포함한다
  CHECK: python tools/check_skillcreator_evals.py content-research
  EXPECT: SKILLCREATOR EVALS OK
  DEPS: tools/check_skillcreator_evals.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T06:05:59.478Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=f570de61324650ca0a665dc5819c5285bb1747f08f08e38b261c4881ee195225; output-bytes=75

- [x] R9: 새 content-research가 v1.6.1 대비 benchmark에서 평균 통과율이 높고 0.8 이상이다(3개 eval 이상, 두 구성 모두 측정)
  CHECK: python tools/check_benchmark.py .workspace/content-research-workspace/iteration-1/benchmark.json --min-evals 3 --min-pass 0.8
  EXPECT: BENCHMARK OK
  DEPS: tools/check_benchmark.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T06:05:59.936Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=45e28d1ebbd2202373e386dbc9119a5da366478b27b46acd9f1b1dab1656a0a5; output-bytes=259

- [x] R10: 사람 검토용 정적 eval 뷰어 HTML이 모든 실행을 포함한다
  CHECK: python tools/check_review_html.py .workspace/content-research-workspace/iteration-1/review.html .workspace/content-research-workspace/iteration-1
  EXPECT: REVIEW HTML OK
  DEPS: tools/check_review_html.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T06:06:00.437Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=cc417072cff40668e2796c607936dda1b2b386873fbf77d9196521d759f24ec2; output-bytes=45

- [x] R11: 계획서 진행 현황·CHANGELOG·분석 문서·handoff(H13 해소 포함)가 content-research 결과(측정값 포함)로 갱신되었다
  EVIDENCE: manual 2026-10-02 — docs/01-plan/skills-upgrade.plan.md 'Phase 1 — content-research' 표(평균 0.977 대 0.946, eval별 점수, 회귀 43개, 다음 generate-shorts), CHANGELOG.md content-research 섹션·7장 실습 샘플 줄, docs/03-analysis/content-research-phase1.analysis.md(§2 측정값과 '차이 작음', §3 결과 후 변경 6건, §4 결함 10건), docs/gate0-handoff.md H13 해소 표시·H10에 content-research 포함. 수치를 benchmark.json·grading.json·timing.json과 대조함
