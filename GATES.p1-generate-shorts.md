# Gates: Phase 1 — generate-shorts 고도화 (계획서 §1.2(7), §4 Phase 1 순서 6, §7.1 사용 범위, D8)

OWNS: plugins/kevin-skills-creator/skills/generate-shorts/**, shared/optional/**, plugins/kevin-skills-practice/skills/practice-samples/samples/generate-shorts/**, plugins/kevin-skills-practice/skills/practice-samples/samples/catalog.json, tools/**, tests/**, .github/workflows/ci.yml, docs/**, CHANGELOG.md, README.md, GATES.p1-generate-shorts.md, .workspace/**

Scope: generate-shorts를 권리를 가진 영상(로컬 파일·자사 채널) 중심으로 바꾸고, 로컬 영상+자막·자막 없는 영상(STT 선택) 입력을 더하며, Windows에서 ffmpeg·한글 폰트·경로가 동작하게 한다. 하이라이트 JSON과 완성 쇼츠를 스크립트로 검증하고(verify), 쿠키 자동 사용과 '우회' 문서를 없앤다. 제3자 방송 자막이던 실습 자료를 자체 제작 강의 영상으로 바꾸고 v1.6.1 대비 평가 결과를 증거로 남긴다.

- [x] V0: this ledger states outcomes that can fail
  CHECK: node C:/Users/Admin/.claude/skills/unlazy/scripts/gate-lint.mjs GATES.p1-generate-shorts.md
  EXPECT: LINT OK
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T07:36:53.023Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=264cc1515d1efb570acc70ad21ed639e4986a09ea05f8f053436bc64a271f31d; output-bytes=170

- [x] V1: 실습 강의 영상(자체 제작)·자막·정답표가 있고, 영상의 길이·해상도·오디오와 자막 시간이 정답표와 맞으며, 제3자 방송 자막 샘플은 실습 자료에서 빠졌다
  CHECK: python tests/check_shorts_practice.py
  EXPECT: SHORTS PRACTICE OK
  DEPS: tests/check_shorts_practice.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T07:36:54.681Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=a2f6e50d4811126f68da9b0534d8da1efa9624637cff269029ce32eb321ce69e; output-bytes=664

- [x] V2: media.py가 ffmpeg를 PATH·환경변수·imageio-ffmpeg 순서로 찾고, ffprobe 없이도 길이·해상도·오디오 유무를 읽으며, Windows 경로를 ffmpeg 필터용으로 이스케이프한다
  CHECK: python tests/check_media.py
  EXPECT: MEDIA OK
  DEPS: tests/check_media.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T07:36:59.894Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=5988d847db0020fa3700ff6f0e3ac1ac7bf812afe769e537a0f13bf940989156; output-bytes=462

- [x] V3: validate_highlights.py가 길이 범위·원본 길이 초과·겹침·자막 시간 역전·자막 범위 초과·제목/후크 길이·필수 필드 누락을 각각 잡고 정상 하이라이트는 통과시킨다(양성 대조)
  CHECK: python tests/check_validate_highlights.py
  EXPECT: HIGHLIGHTS VALIDATE CONTROL OK
  DEPS: tests/check_validate_highlights.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T07:37:06.411Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=6e995783703bba948af75b46eb40e49b86cc61a92718340f6a2b478613f71979; output-bytes=590

- [x] V4: 로컬 영상+자막으로 쇼츠를 끝까지 만들고(Windows, 한글 자막·후크), verify_short.py가 그 결과를 통과시키며 해상도·길이·오디오 없음·검은 화면·오버레이 합성 실패 표시를 잡는다. 두 줄 후크의 줄 사이에 빈 줄이 없고(CRLF 양성 대조), 카드 제목의 획 많은 한글이 뭉개지지 않으며(외곽선 양성 대조), 해시태그가 제목 전체를 붙인 긴 태그가 아니다(benchmark에서 찾은 결함)
  CHECK: python tests/check_shorts_e2e.py
  EXPECT: SHORTS E2E OK
  DEPS: tests/check_shorts_e2e.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T07:38:05.654Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=ca0b4c6c625a37335a4f721fcba699b9cc689699bc467ecbd5e45df482d10dea; output-bytes=890

- [x] V5: 사용 범위 정책 — 브라우저 쿠키를 자동으로 쓰지 않고, 스킬 문서·스크립트에 '봇 감지 우회'·User-Agent 위장·무작위 지연이 없으며, SKILL.md가 URL 입력 전에 권리 확인을 요구한다
  CHECK: python tests/check_shorts_policy.py
  EXPECT: SHORTS POLICY OK
  DEPS: tests/check_shorts_policy.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T07:38:08.220Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=87eab1168e9eac00bd1b6545a91fa02da63d130d8eda79d6703181e4f70e6777; output-bytes=551

- [x] V12: 음성 인식 모델이 메모리 부족으로 실패하면 더 작은 모델로 다시 시도하고 실제 쓴 모델을 남기며, 메모리와 무관한 오류나 가장 작은 모델의 실패는 숨기지 않는다(benchmark에서 찾은 결함)
  CHECK: python tests/check_stt_fallback.py
  EXPECT: STT FALLBACK OK
  DEPS: tests/check_stt_fallback.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T07:38:08.846Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=4a45a9c344f8d683f27e54d10a8f27a5862f22acf59d89b72bd7fce0d54de073; output-bytes=649

- [x] V6: generate-shorts SKILL.md·README가 품질 규약을 충족한다
  CHECK: python tools/check_skill_quality.py generate-shorts
  EXPECT: SKILL QUALITY OK
  DEPS: tools/check_skill_quality.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T07:38:09.725Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=1f88a5b738da62ccfc0050abc6022d5a01da9816b79e97b5d4b7fb25119babdb; output-bytes=44

- [x] V7: 회귀 없음 — Phase 0·앞선 Phase 1 스킬 검증 전체가 통과한다
  CHECK: python tools/run_regression.py
  EXPECT: REGRESSION OK
  DEPS: tools/run_regression.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T07:46:07.427Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=a84f91fe05ff77c5b31f5cc9decf3bbfc516de6ffa4bedbb0dbff6fb36e3c414; output-bytes=2109

- [x] V8: skill-creator 형식 evals.json이 로컬 영상 쇼츠·자막 없는 영상·카드뉴스·권리 미확인 URL 요청을 다루고 실습 영상을 입력으로 쓴다
  CHECK: python tools/check_skillcreator_evals.py generate-shorts
  EXPECT: SKILLCREATOR EVALS OK
  DEPS: tools/check_skillcreator_evals.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T07:46:08.003Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=f60b69b4117a393c7caf7f64957267416cc7bc4fac0fd968aff520dabfbf24c9; output-bytes=74

- [x] V9: 새 generate-shorts가 v1.6.1 대비 benchmark에서 평균 통과율이 높고 0.8 이상이다(3개 eval 이상, 두 구성 모두 측정)
  CHECK: python tools/check_benchmark.py .workspace/generate-shorts-workspace/iteration-1/benchmark.json --min-evals 3 --min-pass 0.8
  EXPECT: BENCHMARK OK
  DEPS: tools/check_benchmark.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T07:46:08.559Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=a9be28cda39d117188eeadc89bc24c269c454ba61d73a39e2812242a90a83ee4; output-bytes=259

- [x] V10: 사람 검토용 정적 eval 뷰어 HTML이 모든 실행을 포함한다
  CHECK: python tools/check_review_html.py .workspace/generate-shorts-workspace/iteration-1/review.html .workspace/generate-shorts-workspace/iteration-1
  EXPECT: REVIEW HTML OK
  DEPS: tools/check_review_html.py
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; verified-at=2026-10-02T07:46:09.364Z; cwd=C:\@Work\claude-cowork-plugin\claude-skills; path=00b5b12e4153/36 entries; EXPECT=matched; output-sha256=ee2c215da5871e0ce25b6406e0749760429615bbda5d525a6a6ef230756efaca; output-bytes=46

- [x] V11: 계획서 진행 현황·CHANGELOG·분석 문서·handoff가 generate-shorts 결과로 갱신되었다
  EVIDENCE: manual 2026-10-02 — docs/01-plan/skills-upgrade.plan.md 'Phase 1 — generate-shorts' 표(평균 1.00 대 0.95, 시간 평균 249초 대 342초, 토큰 13.1만 대 15.6만, 회귀 49개, 다음 narration-video), CHANGELOG.md generate-shorts 섹션·9장 실습 샘플 줄, docs/03-analysis/generate-shorts-phase1.analysis.md(§2 측정값과 '점수 차이가 작은 이유', §3 채점기 1건, §4 결함·수정 10건, §5 남은 것), docs/gate0-handoff.md H3 일부 진행·H10에 generate-shorts 포함·H11 메모리 실패 메모. 수치를 benchmark.json·grading.json·timing.json과 대조함
