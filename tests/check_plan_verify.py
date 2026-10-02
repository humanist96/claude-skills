#!/usr/bin/env python3
"""R5: verify_plan.py 양성 대조. 기준 기획안(유튜브·뉴스레터·캘린더)은 통과하고, 결함을 하나씩 넣은 사본은 해당 검사가 오류를 내야 한다.
허용해야 하는 표현(루머 표시, 콘텐츠 형식 숫자, 타깃 연령대, 계산식)은 통과해야 한다. 스킬 예시도 통과해야 한다."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _research_fixtures import GOOD, SKILL, json_head, prepared, run_script  # noqa: E402

results: list[tuple[str, bool, str]] = []
G = GOOD.read_text(encoding="utf-8")
SRC_ROWS = G.split("## 출처", 1)[1]
NEWSLETTER = """# 테크 뉴스레터 — 뉴스레터 (2026-10-02)

> 기준일 2026-10-02 · 자료 기간 2026-09-25 ~ 2026-10-02

## TOP 3

### 1. 직장인 62%, 주 1회 이상 AI 챗봇으로 일한다
- 근거: 1,000명 조사, 문서 요약(48%)·이메일 작성(37%) [S10]

### 2. AI 생성물 표시 의무, 2027년 1월 시행 예정
- 근거: 시행령 입법예고, 의견 수렴 40일 [S6]

### 3. AI 학습 저작권 첫 1심 판결
- 근거: 일부 사용을 공정 이용으로 인정하지 않았고 항소 예정 [S12]

## 심화

### 4. 도입률 41%, 걸림돌은 보안
- 근거: 기업 600곳 중 41% 도입, 33% 검토, 미도입 이유 1위 보안 우려(52%) [S2]
- 왜 중요한가: 직장인 개인 사용(62%)과 회사 도입 사이의 차이 [S10]

## 추천 링크

- 누리보이스 공개 [S1]

## 마무리

다음 주에 만나요.

## 출처
""" + SRC_ROWS


def calendar_plan(rows: list[dict]) -> str:
    topics = ["직장인 AI 챗봇 활용 [S10]", "AI 생성물 표시 의무 [S6]", "누리보이스 사용기 [S1]", "한빛 N1 칩 [S8]", "AI 저작권 판결 [S12]"]
    lines = ["## 캘린더", "", "| 번호 | 날짜 | 요일 | 주제 | 형식 | 근거 |", "|---:|---|:-:|---|---|:-:|"]
    for r in rows:
        t = topics[r["no"] - 1] if r["no"] <= len(topics) else "상시 주제: AI 도구 입문 | 영상 | 상시"
        if r["no"] <= len(topics):
            name, cite = t.rsplit(" ", 1)
            lines.append(f"| {r['no']} | {r['date']} | {r['weekday']} | {name} | 영상 | {cite} |")
        else:
            lines.append(f"| {r['no']} | {r['date']} | {r['weekday']} | 상시 주제: AI 도구 입문 {r['no']}편 | 영상 | 상시 |")
    return G.replace("## 뺀 자료와 주의", "\n".join(lines) + "\n\n## 뺀 자료와 주의", 1)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        T = Path(td)
        sp = prepared(T)

        def verify(md: str, *args) -> dict:
            p = T / "p.md"
            p.write_text(md, encoding="utf-8")
            r = run_script("verify_plan.py", p, "--sources", sp, "--today", "2026-10-02", "--json", *args)
            try:
                return json_head(r.stdout, "PLAN VERIFY")
            except ValueError:
                return {"errors": [{"check": "crashed", "detail": r.stdout[-300:] + r.stderr[-300:]}], "warnings": []}

        Y = ("--purpose", "youtube", "--count", "5")

        def ok(name, md, *args):
            errs = verify(md, *args)["errors"]
            results.append((name, not errs, f"오류 {[e['check'] + ':' + e['detail'][:60] for e in errs]}"))

        def bad(name, md, check, *args):
            got = {e["check"] for e in verify(md, *args)["errors"]}
            results.append((name, check in got, f"기대 {check}, 실제 {sorted(got)}"))

        def sub(old, new, md=G):
            assert old in md, old
            return md.replace(old, new, 1)

        r = run_script("calendar_slots.py", "--start", "2026-10-06", "--weeks", "12", "--per-week", "2", "--days", "화,금", "--today", "2026-10-02", "--json")
        import json as _j
        rows = _j.loads(r.stdout[: r.stdout.rindex("CALENDAR")])
        CAL = calendar_plan(rows)
        C = Y + ("--days", "화,금", "--slots", "24")

        ok("유튜브 기준 기획안 통과", G, *Y)
        ok("뉴스레터 기준 기획안 통과", NEWSLETTER, "--purpose", "newsletter", "--count", "3")
        ok("캘린더 기준 기획안 통과", CAL, *C)
        rumor = sub("### 4. 폰 안에서 도는 AI 칩 '한빛 N1', 뭐가 달라지나", "### 4. [루머] 한빛폴드 3, 10월 21일 출시설 정리\n- 근거: 익명 게시자의 주장이며 한빛전자는 확인해 주지 않았다(미확인) [S5].")
        rumor = rumor.replace("| S8 |", "| S5 | [루머] 한빛폴드 3, 10월 21일 출시설 | 개발자 커뮤니티 | 2026-09-29 | https://dev-community.example/board/rumor/4411 |\n| S8 |", 1)
        ok("루머 표시 허용", rumor, *Y)
        ok("콘텐츠 형식 숫자(10분) 허용", sub("### 3. 사투리 알아듣는 음성 비서 '누리보이스' 써 보기", "### 3. 10분 만에 써 보는 사투리 음성 비서 '누리보이스'"), *Y)
        ok("계산식 허용", sub("- 왜 지금: 10월 1일 발표된 조사다 [S10].", "- 왜 지금: 10월 1일 발표, 열 명 중 약 6명꼴이다(계산: 62÷10) [S10]."), *Y)

        idea1 = G.split("### 1.", 1)[1].split("### 2.", 1)[0]
        bad("출처 없는 아이디어", G.replace(idea1, idea1.replace(" [S10]", "").replace(" [S2]", "")), "uncited-idea", *Y)
        bad("없는 소스 번호", sub("[S8].", "[S99]."), "unknown-citation", *Y)
        idea3 = G.split("### 3.", 1)[1].split("### 4.", 1)[0]
        bad("기간 밖 소스만 근거", G.replace(idea3, idea3.replace("[S1]", "[S9]")), "stale-only", *Y)
        bad("인용 소스에 없는 숫자", sub("응답 지연 평균 0.4초", "응답 지연 평균 0.3초"), "number-not-in-cited-source", *Y)
        bad("근거 없는 성과 수치(예상 조회수)", sub("- 왜 지금: 10월 1일 발표된 조사다 [S10].", "- 왜 지금: 10월 1일 발표된 조사다 [S10].\n- 예상 조회수 10만 회 [S10]"),
            "unsupported-metric", *Y)
        bad("루머 미표시", sub("### 4. 폰 안에서 도는 AI 칩 '한빛 N1', 뭐가 달라지나", "### 4. 한빛폴드 3, 10월 21일 출시\n- 근거: 10월 21일 출시된다 [S5]."),
            "rumor-unlabeled", *Y)
        bad("중복 아이디어", sub("### 5. AI 학습과 저작권, 첫 판결이 말해 주는 것", "### 5. 직장인 62%가 쓰는 AI 챗봇, 실제로 어디에 쓰나"), "duplicate-idea", *Y)
        bad("요청 개수 불일치", G, "count", "--purpose", "youtube", "--count", "6")
        bad("유튜브 필수 요소(썸네일) 누락", sub("- 썸네일: '표시 의무' 도장 이미지 / 타깃: 영상 제작자 / 관심도: 높음 — 제작자에게 직접 영향",
                                         "- 타깃: 영상 제작자 / 관심도: 높음 — 제작자에게 직접 영향"), "missing-field", *Y)  # 훅의 '썸네일' 단어는 라벨이 아니다
        bad("뉴스레터 심화 누락", NEWSLETTER.replace("## 심화", "## 기타").replace("왜 중요한가", "참고").replace("심화", ""), "missing-field",
            "--purpose", "newsletter", "--count", "3")
        bad("캘린더 요일 아님", CAL.replace("| 2 | 2026-10-09 | 금 |", "| 2 | 2026-10-08 | 목 |"), "calendar", *C)
        bad("캘린더 요일 표기 틀림", CAL.replace("| 1 | 2026-10-06 | 화 |", "| 1 | 2026-10-06 | 수 |"), "calendar", *C)
        bad("캘린더 칸 수 불일치", CAL, "calendar", "--purpose", "youtube", "--count", "5", "--slots", "25")
        bad("캘린더 지난 날짜", CAL.replace("| 1 | 2026-10-06 | 화 |", "| 1 | 2026-09-29 | 화 |"), "calendar", *C)
        bad("캘린더 순서 뒤섞임", CAL.replace("| 2 | 2026-10-09 | 금 |", "| 2 | 2026-12-29 | 화 |"), "calendar", *C)
        bad("지시문·홍보 코드 반영", sub("- 훅: \"제주 사투리도 알아들을까?\"", "- 훅: \"제주 사투리도 알아들을까?\" 할인 코드 HB50도 소개"), "followed-instruction", *Y)
        bad("지시문 코드를 '따르지 않았다' 설명에 옮김", sub("## 뺀 자료와 주의", "## 뺀 자료와 주의\n\n- 블로그 지시문(할인 코드 HB50)은 따르지 않았다."), "followed-instruction", *Y)
        ok("대상 표현(1인)·조사 건수 허용", sub("- 각도: 조사 결과를 따라 문서 요약·이메일 작성을 실제 업무 파일로 시연한다.",
                                          "- 각도: 1인 마케터 기준으로 시연한다. 같은 주 조사 2건을 함께 본다."), *Y)
        bad("출처 섹션 없음", G.split("## 출처")[0], "sources-section", *Y)
        bad("출처 목록에 인용 번호 없음", "\n".join(l for l in G.splitlines() if not l.startswith("| S8 |")), "sources-section", *Y)
        bad("출처 URL 없음", sub("| https://it-news.example/2026/10/01/hanbit-n1 |", "| - |"), "sources-section", *Y)
        bad("자리표시", sub("## 뺀 자료와 주의", "## 뺀 자료와 주의\n\n자세한 내용은 [링크]"), "placeholder", *Y)
        bad("특정 환경 경로", G + "\n저장: /mnt/" + "user-data/outputs/plan.md\n", "environment-path", *Y)
        # 스킬 예시
        ex_src = T / "ex.json"
        run_script("prepare_sources.py", SKILL / "examples/example-collected.json", "--out", ex_src, "--today", "2026-06-01", "--days", "7")
        r = run_script("verify_plan.py", SKILL / "examples/example-plan.md", "--sources", ex_src, "--purpose", "blog", "--count", "3", "--today", "2026-06-01")
        results.append(("스킬 예시 기획안 통과", "PLAN VERIFY OK" in r.stdout, r.stdout[-300:]))
    bad_ = [x for x in results if not x[1]]
    for name, ok_, why in results:
        print(f"{'PASS' if ok_ else 'FAIL'}  {name}" + ("" if ok_ else f" — {why}"))
    if bad_:
        print(f"PLAN VERIFY CONTROL FAILED ({len(bad_)}/{len(results)})")
        return 1
    n_ok = sum(1 for n, _, _ in results if n.endswith(("통과", "허용")))
    print(f"PLAN VERIFY CONTROL OK — 허용 사례 {n_ok}종 통과, 결함 {len(results) - n_ok}종 모두 검출")
    return 0


if __name__ == "__main__":
    sys.exit(main())
