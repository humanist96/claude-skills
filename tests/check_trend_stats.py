#!/usr/bin/env python3
"""D3: trend_stats.py가 조사를 떼고 단어별 언급 소스 수·월별 추이·숫자 근거표를 정답표대로 계산하는지 확인한다."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _collector_fixtures import KEY, SCRIPTS, by_orig, prepared, run_script  # noqa: E402

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "_vendor"))
from numparse import extract, same  # noqa: E402
from trend_stats import strip_josa, tokens  # noqa: E402

results: list[tuple[str, bool, str]] = []


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    josa = {"알룰로스를": "알룰로스", "알룰로스처럼": "알룰로스", "편의점에서": "편의점", "바른식품의": "바른식품", "기능성으로": "기능성",
            "바른제로": "바른제로", "회사는": "회사", "정도로": "정도", "결과가": "결과", "출고량이": "출고량", "제로는": "제로", "원으로": ""}
    got = {w: strip_josa(w) for w in josa}
    results.append(("조사 떼기 12건", got == josa, str({k: v for k, v in got.items() if v != josa[k]})))
    results.append(("서술어·불용어 제외", tokens("가격이 크게 늘었다고 밝혔다. 이번 신제품은") == ["가격", "신제품"], str(tokens("가격이 크게 늘었다고 밝혔다. 이번 신제품은"))))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        T = Path(td)
        sp = prepared(T)
        src = json.loads(sp.read_text(encoding="utf-8"))
        id2orig = {s["id"]: s["orig"] for s in src["sources"]}
        r = run_script("trend_stats.py", sp, "--out", T / "stats.json")
        results.append(("실행", "STATS DONE sources=9" in r.stdout, r.stdout[-200:] + r.stderr[-200:]))
        st = json.loads((T / "stats.json").read_text(encoding="utf-8"))
        results.append(("유지 소스만 사용", sorted(id2orig[i] for i in st["sources_used"]) == KEY["status"]["kept"], str(st["sources_used"])))
        results.append(("월별 건수", st["by_month"] == KEY["months_kept"], str(st["by_month"])))
        for term, srcs in KEY["term_sources"].items():
            results.append((f"'{term}' 언급 소스 {len(srcs)}", st["doc_freq"].get(term) == len(srcs), str(st["doc_freq"].get(term))))
        top = {t["term"]: sorted(id2orig[i] for i in t["ids"]) for t in st["top_terms"]}
        results.append(("상위 단어의 소스 목록", top.get("바른식품") == KEY["term_sources"]["바른식품"], str(top.get("바른식품"))))
        o = by_orig(src)
        facts = {}
        for f in st["facts"]:
            facts.setdefault(id2orig[f["source"]], []).extend(f["numbers"])
        for aid, nums in KEY["numbers"].items():
            if o[aid]["status"] != "kept":
                results.append((f"{aid}(제외) 숫자는 근거표에 없음", aid not in facts, str(facts.get(aid))))
                continue
            pool = [n for t in facts.get(aid, []) for n in extract(t)]
            miss = [n for n in nums if not any(same(x, p) for x in extract(n) for p in pool)]
            results.append((f"{aid} 숫자 근거표", not miss, f"없음 {miss}, 근거표 {facts.get(aid)}"))
        results.append(("논조 비율 없음", not any(k in st for k in ("sentiment", "tone_ratio")), str(list(st))))
    bad = [x for x in results if not x[1]]
    for name, ok, why in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f" — {why}"))
    if bad:
        print(f"TREND STATS FAILED ({len(bad)}/{len(results)})")
        return 1
    print(f"TREND STATS OK — {len(results)}개 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
