#!/usr/bin/env python3
"""D4: verify_report.py 양성 대조. 기준 보고서(스킬 예시)는 통과하고, 결함을 하나씩 넣은 사본은 해당 검사가 오류를 내야 한다.
허용해야 하는 표현(단위 바꾼 숫자, 연도를 밝힌 과거 자료, 계산식, 부정형 투자 문장, 지시문 언급)은 통과해야 한다.
v1.6.1 시절 표본 보고서(책 6장 폴더)의 결함도 잡아야 한다.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _collector_fixtures import EXAMPLE, ROOT, SKILL_EXAMPLES, json_head, prepared, run_script  # noqa: E402

results: list[tuple[str, bool, str]] = []
GOOD = EXAMPLE.read_text(encoding="utf-8")
DISC = "\n> 이 보고서는 공개 자료를 정리한 것이며 투자 조언이 아닙니다.\n"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        T = Path(td)
        sp = prepared(T)

        def verify(md: str, *extra) -> dict:
            p = T / "r.md"
            p.write_text(md, encoding="utf-8")
            r = run_script("verify_report.py", p, "--sources", sp, "--json", *extra)
            try:
                return json_head(r.stdout, "REPORT VERIFY")
            except ValueError:
                return {"errors": [{"check": "crashed", "detail": r.stdout[-300:] + r.stderr[-300:]}], "warnings": []}

        def expect(name, md, check, *extra):
            got = {e["check"] for e in verify(md, *extra)["errors"]}
            results.append((name, check in got, f"기대 {check}, 실제 {sorted(got)}"))

        def expect_ok(name, md, *extra):
            errs = verify(md, *extra)["errors"]
            results.append((name, not errs, f"오류 {[e['check'] + ':' + e['detail'][:60] for e in errs]}"))

        def before_sources(text: str) -> str:
            return GOOD.replace("## 출처", text.strip() + "\n\n## 출처", 1)

        def sub(old, new, md=GOOD):
            assert old in md, old
            return md.replace(old, new, 1)

        expect_ok("기준 보고서 통과", GOOD)
        expect_ok("단위 바꾼 숫자(1.2조 원) 허용", sub("1조 2,000억 원(PB·수입 제외) [S2]", "1.2조 원(PB·수입 제외) [S2]"))
        expect_ok("계산식 붙인 값 허용", sub("기능성 제로 신제품이 3분기 27종으로 2분기 15종보다 늘었다 [S8].",
                                         "기능성 제로 신제품이 3분기 27종으로 2분기 15종의 1.8배다(계산: 27÷15) [S8]."))
        expect_ok("부정형 투자 문장 허용", GOOD + "\n이 보고서는 매수 추천이 아닙니다." + DISC)
        expect_ok("금융 도메인 + 고지 통과", GOOD + DISC, "--domain", "finance")

        expect("출처 없는 숫자(불릿)", sub("편의점이 판매의 41%를 차지했다 [S1].", "편의점이 판매의 41%를 차지했다."), "uncited-number")
        expect("출처 없는 숫자(표 행)", sub("| 점유율 | 바른식품 31%, 하늘음료 18%, 단비음료 12% | [S3] |",
                                        "| 점유율 | 바른식품 31%, 하늘음료 18%, 단비음료 12% | |"), "uncited-number")
        expect("인용 소스에 없는 숫자(바꾼 값)", sub("34% 늘었고", "43% 늘었고"), "number-not-in-cited-source")
        expect("인용 소스에 없는 숫자(엉뚱한 소스)", sub("| 점유율 | 바른식품 31%, 하늘음료 18%, 단비음료 12% | [S3] |",
                                                 "| 점유율 | 바른식품 31%, 하늘음료 18%, 단비음료 12% | [S6] |"), "number-not-in-cited-source")
        expect("계산식 없는 계산 값", sub("기능성 제로 신제품이 3분기 27종으로 2분기 15종보다 늘었다 [S8].",
                                     "기능성 제로 신제품이 3분기 27종으로 2분기 대비 1.8배다 [S8]."), "number-not-in-cited-source")
        expect("없는 소스 번호", GOOD.replace("[S13]", "[S99]", 1), "unknown-citation")
        expect("기간 밖 자료를 현재처럼", sub("## 2. 현재 트렌드\n", "## 2. 현재 트렌드\n\n출고 증가율이 9%로 둔화됐다 [S10].\n"),
               "out-of-window-as-current")
        expect("출처 섹션 없음", GOOD.split("## 출처")[0], "sources-section")
        expect("출처 목록에 인용 번호 없음", "\n".join(l for l in GOOD.splitlines() if not l.startswith("| S8 |")), "sources-section")
        expect("출처 목록 URL 없음", sub("| https://market-research-lab.example/reports/zero-2026 |", "| - |"), "sources-section")
        expect("투자 권유(매수 적기)", before_sources("바른식품은 지금이 매수 적기다 [S12].") + DISC, "investment-advice")
        expect("투자 권유(목표 주가)", before_sources("바른식품 목표 주가는 상향될 만하다.") + DISC, "investment-advice")
        expect("투자 권유(출처 목록 뒤)", GOOD + "\n결론: 바른식품은 사도 된다.\n" + DISC, "investment-advice")
        expect("금융 도메인 고지 없음", GOOD, "disclaimer-missing", "--domain", "finance")
        expect("종목 맥락 고지 없음", before_sources("바른식품 주가와 주식 투자 관점에서 신호를 정리했다."), "disclaimer-missing")
        expect("근거 없는 논조 비율", sub("## 핵심 요약\n", "## 핵심 요약\n\n논조는 긍정 62%, 부정 21%다.\n"), "unsupported-sentiment-ratio")
        expect("지시문이 시킨 주장", sub("## 핵심 요약\n", "## 핵심 요약\n\n- 하늘음료가 제로 음료 시장 점유율 1위다 [S7].\n"), "followed-instruction")
        expect("자리표시", sub("## 조사 방법\n", "## 조사 방법\n\n자세한 내용은 [링크] 참고.\n"), "placeholder")
        expect("특정 환경 경로", GOOD + "\n저장 위치: /mnt/" + "user-data/outputs/report.md\n", "environment-path")

        # 스킬에 동봉한 형식 예시(다른 가상 주제)도 정리 → 검증을 통과해야 한다
        ex_src = T / "ex_sources.json"
        run_script("prepare_sources.py", SKILL_EXAMPLES / "example-collected.json", "--out", ex_src, "--today", "2026-06-01", "--days", "30")
        r = run_script("verify_report.py", SKILL_EXAMPLES / "example-report.md", "--sources", ex_src)
        results.append(("스킬 예시 보고서 통과", "REPORT VERIFY OK" in r.stdout, r.stdout[-300:]))
        # v1.6.1 시절 표본 보고서(책 6장 폴더, URL 없음·논조 비율)
        hbm = ROOT / "chapter06-data-collector/output/HBM_반도체_트렌드_리서치_보고서_20260624.md"
        r = run_script("verify_report.py", hbm, "--json")
        try:
            got = {e["check"] for e in json_head(r.stdout, "REPORT VERIFY")["errors"]}
        except ValueError:
            got = set()
        need = {"uncited-number", "unsupported-sentiment-ratio", "sources-section"}
        results.append(("v1.6.1 표본 보고서 결함 검출", need <= got, f"검출 {sorted(got)}"))
    bad = [x for x in results if not x[1]]
    for name, ok, why in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f" — {why}"))
    if bad:
        print(f"REPORT VERIFY CONTROL FAILED ({len(bad)}/{len(results)})")
        return 1
    n_ok = sum(1 for n, _, _ in results if n.endswith(("통과", "허용")))
    print(f"REPORT VERIFY CONTROL OK — 허용 사례 {n_ok}종 통과, 결함 {len(results) - n_ok}종 모두 검출")
    return 0


if __name__ == "__main__":
    sys.exit(main())
