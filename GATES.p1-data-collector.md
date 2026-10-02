# Gates: Phase 1 — data-collector 고도화 (계획서 §1.2(5), §4 Phase 1 순서 5)

OWNS: plugins/kevin-skills-book/skills/data-collector/**, plugins/kevin-skills-practice/skills/practice-samples/samples/data-collector/**, plugins/kevin-skills-practice/skills/practice-samples/samples/catalog.json, tools/**, tests/**, .github/workflows/ci.yml, docs/**, CHANGELOG.md, README.md, GATES.p1-data-collector.md, .workspace/**

Scope: data-collector를 "범위·리서치 플랜 → 수집(WebSearch·WebFetch 또는 받은 자료) → 소스 정리(중복·기간·신뢰 등급·지시문 표시) → Python 통계 → 교차 검증 → 출처 각주가 달린 보고서 → 자동 검증"으로 재설계한다. 사전 단어 센티먼트와 컨테이너 전용 경로를 없애고, 자동화 패키지(모드 2)는 템플릿 복사와 오프라인 시험 실행으로 검증하며, 실습 자료와 정답표를 갖추고 v1.6.1 대비 평가 결과를 증거로 남긴다. content-research 통합(D1)은 이 원장 범위 밖이며 handoff로 남긴다.

- [x] D0: this ledger states outcomes that can fail
  CHECK: node C:/Users/Admin/.claude/skills/unlazy/scripts/gate-lint.mjs GATES.p1-data-collector.md
  EXPECT: LINT OK
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T04:59:20.414Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=5177726fada9761bebfe9e59dd6827882a10fd671b04394c9aa0b0630e54bc8d; output-bytes=169

- [x] D1: 실습 기사 묶음(자체 작성 가상 기사)과 정답표가 재현 가능하게 생성되고, 정답표의 기간 밖·중복·상충 수치·지시문 문장이 실제 기사 내용과 일치한다
  CHECK: python tests/check_collector_practice.py
  EXPECT: COLLECTOR PRACTICE OK
  DEPS: tests/check_collector_practice.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T04:59:21.140Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=5a19fa4aa56fda2b60b309b0006c580dcfbcde2268e132813305ee74917ebae2; output-bytes=1160

- [x] D2: prepare_sources.py가 수집 자료를 S번호 소스 목록으로 정리하며 URL 중복·제목 유사 중복·기간 밖·날짜 없음·신뢰 등급·지시문처럼 보이는 문장을 정답표대로 판정한다
  CHECK: python tests/check_prepare_sources.py
  EXPECT: PREPARE SOURCES OK
  DEPS: tests/check_prepare_sources.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T04:59:23.179Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=2c14a69c15d08f777b245ac3fb9247a6b65e0d44ba0eef775c82430a1469ebce; output-bytes=791

- [x] D3: trend_stats.py가 한국어 조사를 떼고 단어별 언급 소스 수·주차별 추이·상승 단어·숫자 근거표를 정답표대로 계산한다
  CHECK: python tests/check_trend_stats.py
  EXPECT: TREND STATS OK
  DEPS: tests/check_trend_stats.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T04:59:24.312Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=74f143be0912278c05ab3c928f9660f4d0fbfe87329e0d705b7b6a6956e6a618; output-bytes=684

- [x] D4: verify_report.py가 출처 없는 숫자·인용 소스에 없는 숫자·없는 소스 번호·제외된 소스 인용·출처 목록 누락·투자 권유·면책 누락·근거 없는 논조 비율·지시문 주장 반영·자리표시를 각각 잡고, 기준 보고서는 통과시키며, v1.6.1 표본 보고서의 결함을 검출한다(양성 대조)
  CHECK: python tests/check_report_verify.py
  EXPECT: REPORT VERIFY CONTROL OK
  DEPS: tests/check_report_verify.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T04:59:32.443Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=38feb193c8abcdd4ffb3371d53293c48c4e18f31725fc99f13bd6d0876a764db; output-bytes=1048

- [x] D5: build_pipeline.py가 자동화 패키지 필수 파일을 만들고, 워크플로·설정 YAML이 유효하며, 웹훅이 비어 있고, 오프라인 피드로 시험 실행하면 보고서가 생성되며, 도메인 프로필마다 한국어 뉴스 소스가 있다(변조 대조 포함)
  CHECK: python tests/check_build_pipeline.py
  EXPECT: PIPELINE OK
  DEPS: tests/check_build_pipeline.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T04:59:40.178Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=dd4495080d88e1b85b39cf988ebbaf6b80d40cf6724ff242ae5749c84bdf4148; output-bytes=1560

- [x] D6: data-collector SKILL.md·README가 품질 규약을 충족한다
  CHECK: python tools/check_skill_quality.py data-collector
  EXPECT: SKILL QUALITY OK
  DEPS: tools/check_skill_quality.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T04:59:40.663Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=65c797c26e90755f1cd32df98530b50e81f4df8ca9836bf929cb494261065d72; output-bytes=43

- [x] D7: 회귀 없음 — Phase 0·앞선 Phase 1 스킬 검증 전체가 통과한다
  CHECK: python tools/run_regression.py
  EXPECT: REGRESSION OK
  DEPS: tools/run_regression.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T05:06:12.116Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=035de3bf3fe335cdb369346c5c8cb67e569e48a60740a857c975cb2c93c87538; output-bytes=1672

- [x] D8: skill-creator 형식 evals.json이 오프라인 보고서·투자 질문·자동화 패키지·실시간 웹 수집을 다루고 실습 기사 묶음을 입력으로 쓴다
  CHECK: python tools/check_skillcreator_evals.py data-collector
  EXPECT: SKILLCREATOR EVALS OK
  DEPS: tools/check_skillcreator_evals.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T05:06:12.903Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=91deeccfaaf262ca1ca17d611040ab8746ba7d19966d19251055ffa428d79a0b; output-bytes=73

- [x] D9: 새 data-collector가 v1.6.1 대비 benchmark에서 평균 통과율이 높고 0.8 이상이다(3개 eval 이상, 두 구성 모두 측정)
  CHECK: python tools/check_benchmark.py .workspace/data-collector-workspace/iteration-1/benchmark.json --min-evals 3 --min-pass 0.8
  EXPECT: BENCHMARK OK
  DEPS: tools/check_benchmark.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T05:06:13.578Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=f3daa01f95c603ad0734001f3aedb80431d22c1f20a864497ca81beb2266cbcb; output-bytes=259

- [x] D10: 사람 검토용 정적 eval 뷰어 HTML이 모든 실행을 포함한다
  CHECK: python tools/check_review_html.py .workspace/data-collector-workspace/iteration-1/review.html .workspace/data-collector-workspace/iteration-1
  EXPECT: REVIEW HTML OK
  DEPS: tools/check_review_html.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T05:06:14.192Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=b5d2c2b8e7395004c38c04af2b53292d0c09dc7da1f4cdfc5964712126578362; output-bytes=45

- [x] D11: 계획서 진행 현황·CHANGELOG·분석 문서·handoff가 data-collector 결과(측정값 포함)로 갱신되었다
  EVIDENCE: manual 2026-10-02 — docs/01-plan/skills-upgrade.plan.md 'Phase 1 — data-collector' 표(평균 1.00 대 0.805, eval별 점수, 시간 중앙값 184초 대 232초, 회귀 39개), CHANGELOG.md data-collector 섹션·6장 실습 샘플 줄, docs/03-analysis/data-collector-phase1.analysis.md(§2 측정값, §3 채점기 수정 5건과 수정 전 객관 점수 24/27 대 19/27, §4 결함 11건), docs/gate0-handoff.md H13(content-research 통합) 추가·H10에 data-collector 포함. 각 수치를 benchmark.json·grading.json·timing.json과 대조함
