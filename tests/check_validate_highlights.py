#!/usr/bin/env python3
"""V3: validate_highlights.py 양성 대조. 정상 하이라이트는 통과하고, 결함을 하나씩 넣은 사본은 해당 검사가 오류를 낸다."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shorts_fixtures import KEY, good_highlights, run_script  # noqa: E402

results: list[tuple[str, bool, str]] = []


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    G = good_highlights()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        T = Path(td)
        tr = T / "transcript.json"
        from _shorts_fixtures import TIMINGS  # noqa: E402
        tr.write_text(json.dumps({"chunks": [{"text": l["text"], "timestamp": [l["start"], l["end"]]} for l in TIMINGS]},
                                 ensure_ascii=False), encoding="utf-8")

        def check(hl) -> dict:
            p = T / "h.json"
            p.write_text(json.dumps(hl, ensure_ascii=False), encoding="utf-8")
            r = run_script("validate_highlights.py", p, "--duration", KEY["duration"], "--transcript", tr, "--json")
            try:
                return json.loads(r.stdout[: r.stdout.rindex("HIGHLIGHTS")])
            except ValueError:
                return {"errors": [{"check": "crashed", "detail": r.stdout[-200:] + r.stderr[-200:]}], "warnings": []}

        def ok(name, hl):
            out = check(hl)
            results.append((name, not out["errors"], f"오류 {[e['check'] + ':' + e['detail'][:50] for e in out['errors']]}"))

        def bad(name, hl, chk):
            got = {e["check"] for e in check(hl)["errors"]}
            results.append((name, chk in got, f"기대 {chk}, 실제 {sorted(got)}"))

        def mod(fn):
            h = copy.deepcopy(G)
            fn(h)
            return h

        ok("정상 하이라이트 3개 통과", G)
        ok("자막 생략([]) 허용", mod(lambda h: h[0].__setitem__("subtitles", [])))
        bad("목록이 아님", {"start": 1}, "schema")
        bad("subtitles 필드 없음", mod(lambda h: h[0].pop("subtitles")), "schema")
        bad("hook 필드 없음", mod(lambda h: h[1].pop("hook")), "schema")
        bad("15초 미만", mod(lambda h: h[0].__setitem__("end", h[0]["start"] + 10)), "length")
        bad("60초 초과", mod(lambda h: (h[2].__setitem__("start", 30.0), h[2].__setitem__("end", 100.0))), "length")
        bad("원본 길이 초과", mod(lambda h: h[2].__setitem__("end", KEY["duration"] + 5)), "range")
        bad("start >= end", mod(lambda h: h[0].__setitem__("end", h[0]["start"])), "range")
        bad("구간 겹침", mod(lambda h: h[1].__setitem__("start", h[0]["end"] - 5)), "overlap")
        bad("index 중복", mod(lambda h: h[1].__setitem__("index", 1)), "overlap")
        bad("제목 28자 초과", mod(lambda h: h[0].__setitem__("title", "가" * 29)), "title")
        bad("후크 20자 초과", mod(lambda h: h[0].__setitem__("hook", "나" * 21)), "hook")
        bad("자막이 구간 길이를 넘음(절대 시간을 씀)", mod(lambda h: h[0]["subtitles"].append(
            {"start": h[0]["start"] + 1, "end": h[0]["start"] + 3, "text": "절대 시간"})), "subtitle-time")
        bad("자막 시간 역전", mod(lambda h: h[0]["subtitles"][0].__setitem__("end", 0.0)), "subtitle-time")
        bad("자막 겹침", mod(lambda h: h[0]["subtitles"][1].__setitem__("start", h[0]["subtitles"][0]["start"])), "subtitle-time")
        w = check(mod(lambda h: h[0].__setitem__("start", h[0]["start"] + 4)))
        results.append(("말 중간 시작은 경계 경고", any(x["check"] == "boundary" for x in w["warnings"]), str(w["warnings"])[:200]))
    bad_ = [x for x in results if not x[1]]
    for name, ok_, why in results:
        print(f"{'PASS' if ok_ else 'FAIL'}  {name}" + ("" if ok_ else f" — {why}"))
    if bad_:
        print(f"HIGHLIGHTS VALIDATE CONTROL FAILED ({len(bad_)}/{len(results)})")
        return 1
    n_ok = sum(1 for n, _, _ in results if n.endswith(("통과", "허용")))
    print(f"HIGHLIGHTS VALIDATE CONTROL OK — 허용 사례 {n_ok}종 통과, 결함·경고 {len(results) - n_ok}종 모두 검출")
    return 0


if __name__ == "__main__":
    sys.exit(main())
