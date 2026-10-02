#!/usr/bin/env python3
"""D1: 실습 기사 묶음과 정답표가 재현 가능하고, 정답표의 내용이 기사와 맞는지 기사 텍스트로 직접 확인한다.

정답표를 스크립트 결과로 만들지 않았는지 보려고, 여기서는 data-collector 스크립트를 쓰지 않고 문자열로만 확인한다.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _collector_fixtures import ARTICLES, KEY, PRACTICE, ROOT  # noqa: E402

results: list[tuple[str, bool, str]] = []


def art(aid: str) -> tuple[dict, str]:
    raw = (ARTICLES / f"{aid}.md").read_text(encoding="utf-8")
    head, body = raw.split("\n---\n", 1)
    meta = dict(l.split(": ", 1) if ": " in l else (l.rstrip(":"), "") for l in head.strip("-\n").splitlines())
    return meta, body


def flat(s: str) -> str:
    return re.sub(r"\s+", "", s)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    r = subprocess.run([sys.executable, str(ROOT / "tools/dev/make_collector_practice.py"), "--check"], capture_output=True, text=True,
                       encoding="utf-8")
    results.append(("재현 가능", "REPRODUCIBLE" in r.stdout, r.stdout[-200:]))
    ids = sorted(p.stem for p in ARTICLES.glob("A*.md"))
    results.append(("기사 13건", len(ids) == KEY["articles"] == 13, str(ids)))
    metas = {a: art(a) for a in ids}
    results.append(("모든 링크가 예약 도메인(.example)", all(".example/" in m["url"] for m, _ in metas.values()), ""))
    results.append(("가상 기사 안내", "지어낸 것" in (ARTICLES / "README.md").read_text(encoding="utf-8"), ""))
    for aid, nums in KEY["numbers"].items():
        m, body = metas[aid]
        miss = [n for n in nums if flat(n) not in flat(m["title"] + body)]
        results.append((f"{aid} 숫자 {len(nums)}개가 기사에 있음", not miss, f"없음: {miss}"))
    st = KEY["status"]
    a4, a5 = metas["A04"][0]["url"], metas["A05"][0]["url"]
    results.append(("A05는 A04 URL + 추적 파라미터", a5.startswith(a4 + "?") and "utm_" in a5, a5))
    body = lambda a: flat(re.sub(r"^#.*$", "", metas[a][1], flags=re.M))  # noqa: E731 — 제목 줄 제외
    results.append(("A09 본문은 A08 본문의 일부", body("A09") in body("A08"), ""))
    since = KEY["window"]["since"]
    results.append(("A10만 기간 밖", [a for a, (m, _) in metas.items() if m["date"] and m["date"] < since] == st["out_of_window"], ""))
    results.append(("A11만 날짜 없음", [a for a, (m, _) in metas.items() if not m["date"]] == st["undated"], ""))
    kept = set(ids) - set(st["duplicate"]) - set(st["out_of_window"]) - set(st["undated"])
    results.append(("유지 9건", sorted(kept) == st["kept"], str(sorted(kept))))
    for v in KEY["conflict"]["values"]:
        results.append((f"상충 수치 {v['value']}가 {v['source']}에", flat(v["value"]) in flat(metas[v["source"]][1]), ""))
    for aid, phrase in KEY["instruction_like"].items():
        results.append((f"{aid}에 지시문", phrase in metas[aid][1] and KEY["false_claim_from_instruction"] in metas[aid][1], ""))
    tl = KEY["true_leader"]
    results.append(("실제 1위 근거", f"{tl['company']}이 {tl['share']}로 1위" in metas[tl["source"]][1], ""))
    for term, srcs in KEY["term_sources"].items():
        got = sorted(a for a in kept if term in metas[a][0]["title"] + metas[a][1])
        results.append((f"단어 '{term}' 언급 기사", got == srcs, f"실제 {got}"))
    months: dict[str, int] = {}
    for a in kept:
        months[metas[a][0]["date"][:7]] = months.get(metas[a][0]["date"][:7], 0) + 1
    results.append(("월별 유지 건수", dict(sorted(months.items())) == KEY["months_kept"], str(months)))
    cat = json.loads((PRACTICE.parent / "catalog.json").read_text(encoding="utf-8"))
    sets = {s["id"]: s for s in cat["sets"]}
    for sid in ("collector-articles", "collector-answer-key"):
        s = sets.get(sid)
        ok = bool(s) and all(list(PRACTICE.parent.glob(f)) for f in s["files"])
        results.append((f"catalog {sid}", ok, str(s)[:200]))
    bad = [x for x in results if not x[1]]
    for name, ok, why in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f" — {why}"))
    if bad:
        print(f"COLLECTOR PRACTICE FAILED ({len(bad)}/{len(results)})")
        return 1
    print(f"COLLECTOR PRACTICE OK — {len(results)}개 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
