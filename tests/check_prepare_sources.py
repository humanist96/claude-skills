#!/usr/bin/env python3
"""D2: prepare_sources.py의 판정(중복·기간·날짜 없음·등급·지시문)이 정답표와 같은지, 입력 형식·URL·날짜 처리를 확인한다."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _collector_fixtures import ARTICLES, KEY, ROOT as ROOT_DIR, SCRIPTS, by_orig, prepared, run_script  # noqa: E402

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "_vendor"))
from prepare_sources import canonical_url, parse_date  # noqa: E402

results: list[tuple[str, bool, str]] = []


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        T = Path(td)
        src = json.loads(prepared(T).read_text(encoding="utf-8"))
        o = by_orig(src)
        st = KEY["status"]
        got = {a: s["status"] for a, s in o.items()}
        want = {**{a: "kept" for a in st["kept"]}, **{a: "duplicate" for a in st["duplicate"]},
                **{a: "out_of_window" for a in st["out_of_window"]}, **{a: "undated" for a in st["undated"]}}
        results.append(("상태 13건 정답표와 일치", got == want, f"다름: {[(a, got.get(a), w) for a, w in want.items() if got.get(a) != w]}"))
        id2orig = {s["id"]: a for a, s in o.items()}
        for dup, orig in st["duplicate"].items():
            s = o[dup]
            results.append((f"{dup} → {orig} 중복({KEY['duplicate_reason'][dup]})",
                            id2orig.get(s.get("duplicate_of")) == orig and s.get("duplicate_reason") == KEY["duplicate_reason"][dup],
                            f"{s.get('duplicate_of')} {s.get('duplicate_reason')}"))
        tiers = {a: s["tier"] for a, s in o.items()}
        results.append(("신뢰 등급 정답표와 일치", tiers == KEY["tiers"], f"다름: {[(a, tiers[a], t) for a, t in KEY['tiers'].items() if tiers.get(a) != t]}"))
        flagged = {a: s["flags"] for a, s in o.items() if s["flags"]}
        results.append(("지시문 FLAG는 A07 한 건", list(flagged) == list(KEY["instruction_like"]) and
                        KEY["instruction_like"]["A07"] in flagged.get("A07", [{}])[0].get("text", ""), str(list(flagged))))
        sm = src["summary"]
        results.append(("요약 집계", sm["status"] == {"duplicate": 2, "kept": 9, "out_of_window": 1, "undated": 1}
                        and sm["kept_by_month"] == KEY["months_kept"], json.dumps(sm, ensure_ascii=False)[:200]))
        # 기간을 주지 않으면 기간 밖 판정이 없어야 한다(대조)
        r = run_script("prepare_sources.py", ARTICLES, "--out", T / "nowin.json", "--today", KEY["as_of"])
        results.append(("기간 없으면 out_of_window 0", "out_of_window=0" in r.stdout and "kept=10" in r.stdout, r.stdout[-120:]))
        # JSON 입력: v1 collected_data.json 형식, 리스트, JSONL
        v1 = [{"source": "검색", "status": "success", "data": [
            {"title": "기사 하나", "link": "https://www.news.example/a/1?utm_source=x", "summary": "매출 120억 원", "published": "2026-09-30"},
            {"title": "기사 하나", "link": "https://news.example/a/1/", "summary": "매출 120억 원", "published": "2026-09-30"},
            {"title": "다른 기사", "link": "https://blog.naver.com/x/2", "summary": "후기", "published": "3일 전"}]}]
        (T / "v1.json").write_text(json.dumps(v1, ensure_ascii=False), encoding="utf-8")
        r = run_script("prepare_sources.py", T / "v1.json", "--out", T / "o.json", "--today", "2026-10-02", "--days", "30")
        o2 = json.loads((T / "o.json").read_text(encoding="utf-8"))["sources"]
        results.append(("v1 형식 입력: URL 중복·상대 날짜·도메인 등급", [s["status"] for s in o2] == ["kept", "duplicate", "kept"]
                        and o2[2]["date"] == "2026-09-29" and o2[2]["tier"] == "D" and o2[0]["publisher"] == "검색", r.stdout[-300:]))
        (T / "x.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in v1[0]["data"]), encoding="utf-8")
        r = run_script("prepare_sources.py", T / "x.jsonl", "--out", T / "o3.json", "--today", "2026-10-02")
        results.append(("JSONL 입력", "kept=2 duplicate=1" in r.stdout, r.stdout[-120:]))
        (T / "empty.json").write_text("[]", encoding="utf-8")
        r = run_script("prepare_sources.py", T / "empty.json", "--out", T / "o4.json")
        results.append(("빈 입력은 실패로", r.returncode == 1, r.stdout[-120:]))
    # RSS 피드 파일 입력(content-research 실습 피드, R3)
    import json as _json
    rkey = _json.loads((ROOT_DIR / "plugins/kevin-skills-practice/skills/practice-samples/samples/content-research/answer_key.json").read_text(encoding="utf-8"))
    feed = ROOT_DIR / "plugins/kevin-skills-practice/skills/practice-samples/samples/content-research/inputs/주간_테크뉴스.xml"
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        out = Path(td) / "rss.json"
        r = run_script("prepare_sources.py", feed, "--out", out, "--today", rkey["as_of"], "--since", rkey["window"]["since"],
                       "--until", rkey["window"]["until"])
        rs = {s["orig"]: s for s in _json.loads(out.read_text(encoding="utf-8"))["sources"]} if out.is_file() else {}
        st = rkey["status"]
        want = {**{a: "kept" for a in st["kept"]}, **{a: "duplicate" for a in st["duplicate"]}, **{a: "out_of_window" for a in st["out_of_window"]}}
        got = {a: s["status"] for a, s in rs.items()}
        results.append(("RSS: 상태 12건 정답표와 일치", got == want, f"{r.stdout[-200:]} 다름 {[(a, got.get(a), w) for a, w in want.items() if got.get(a) != w]}"))
        id2orig = {s["id"]: a for a, s in rs.items()}
        results.append(("RSS: 중복 원본·이유", all(id2orig.get(rs[d].get("duplicate_of")) == o and rs[d].get("duplicate_reason") == rkey["duplicate_reason"][d]
                                                 for d, o in st["duplicate"].items()) if rs else False, ""))
        results.append(("RSS: 등급(<category>→kind)", {a: s["tier"] for a, s in rs.items()} == rkey["tiers"], ""))
        results.append(("RSS: 매체(<source>)", rs.get("R03", {}).get("publisher") == "바다소프트(보도자료)", str(rs.get("R03", {}).get("publisher"))))
        results.append(("RSS: 지시문 FLAG는 R07", [a for a, s in rs.items() if s["flags"]] == list(rkey["instruction_like"]), ""))
    cases = [("https://www.A.example/x/?utm_source=a&id=3#top", "https://a.example/x?id=3"),
             ("http://m.a.example/x?fbclid=1", "https://a.example/x")]
    for raw, want in cases:
        results.append((f"URL 정규화 {raw}", canonical_url(raw) == want, canonical_url(raw)))
    ref = date(2026, 10, 2)
    dcases = [("2026.07.08", date(2026, 7, 8)), ("2026년 7월 8일", date(2026, 7, 8)), ("Wed, 08 Jul 2026 10:00:00 +0900", date(2026, 7, 8)),
              ("Jul 8, 2026", date(2026, 7, 8)), ("2026-07-08T09:00:00Z", date(2026, 7, 8)), ("2시간 전", ref), ("어제", date(2026, 10, 1)),
              ("", None), ("날짜 미상", None)]
    for raw, want in dcases:
        got = parse_date(raw, ref)
        results.append((f"날짜 '{raw}'", got == want, str(got)))
    bad = [x for x in results if not x[1]]
    for name, ok, why in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f" — {why}"))
    if bad:
        print(f"PREPARE SOURCES FAILED ({len(bad)}/{len(results)})")
        return 1
    print(f"PREPARE SOURCES OK — {len(results)}개 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
