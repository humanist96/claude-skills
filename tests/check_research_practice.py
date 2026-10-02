#!/usr/bin/env python3
"""R2: 실습 피드와 정답표가 재현 가능하고, 정답표 내용이 피드와 맞는지 표준 라이브러리 XML 파싱으로 직접 확인한다.
(정답표를 스킬 스크립트 결과로 만들지 않았는지 보려고 prepare_sources를 쓰지 않는다)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _research_fixtures import FEED, KEY, PRACTICE, ROOT  # noqa: E402

results: list[tuple[str, bool, str]] = []


def flat(s: str) -> str:
    return re.sub(r"\s+", "", s)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    r = subprocess.run([sys.executable, str(ROOT / "tools/dev/make_research_practice.py"), "--check"], capture_output=True, text=True, encoding="utf-8")
    results.append(("재현 가능", "REPRODUCIBLE" in r.stdout, r.stdout[-200:]))
    root = ET.fromstring(FEED.read_bytes())
    items = {}
    for it in root.iter("item"):
        items[it.findtext("guid")] = {"title": it.findtext("title"), "url": it.findtext("link"), "kind": it.findtext("category"),
                                      "pub": it.findtext("source"), "text": it.findtext("description"),
                                      "date": parsedate_to_datetime(it.findtext("pubDate")).date().isoformat()}
    results.append(("항목 12건", len(items) == KEY["items"] == 12, str(list(items))))
    results.append(("모든 링크가 예약 도메인(.example)", all(".example/" in v["url"] for v in items.values()), ""))
    results.append(("가상 기사 안내", "지어낸 것" in root.findtext("channel/description"), ""))
    for rid, nums in KEY["numbers"].items():
        miss = [n for n in nums if flat(n) not in flat(items[rid]["title"] + items[rid]["text"])]
        results.append((f"{rid} 숫자 {len(nums)}개가 피드에 있음", not miss, f"없음 {miss}"))
    st = KEY["status"]
    results.append(("R11 = R01 URL + 추적 파라미터", items["R11"]["url"].startswith(items["R01"]["url"] + "?") and "utm_" in items["R11"]["url"], ""))
    results.append(("R04 본문 = R03 본문", items["R04"]["text"] == items["R03"]["text"], ""))
    since = KEY["window"]["since"]
    results.append(("R09만 기간 밖", [k for k, v in items.items() if v["date"] < since] == st["out_of_window"], ""))
    kept = sorted(set(items) - set(st["duplicate"]) - set(st["out_of_window"]))
    results.append(("유지 9건", kept == st["kept"], str(kept)))
    code = KEY["promo_code"]
    with_code = sorted(k for k, v in items.items() if code in v["text"])
    results.append((f"홍보 코드 {code}는 R03·R04·R07에만", with_code == ["R03", "R04", "R07"], str(with_code)))
    results.append(("R07 지시문", KEY["instruction_like"]["R07"] in items["R07"]["text"], ""))
    rm = KEY["rumor"]
    results.append(("R05 루머·커뮤니티", "루머" in items[rm["source"]]["title"] and items[rm["source"]]["kind"] == "community", ""))
    kinds = {k: v["kind"] for k, v in items.items()}
    tier_by_kind = {"news": "B", "research": "B", "press_release": "D", "community": "D", "blog": "D"}
    results.append(("등급 정답 = 종류 기준", {k: tier_by_kind[v] for k, v in kinds.items()} == KEY["tiers"], ""))
    cal = KEY["calendar_eval"]
    results.append(("캘린더 정답 24칸", cal["slots"] == cal["weeks"] * cal["per_week"] == 24, ""))
    cat = json.loads((PRACTICE.parent / "catalog.json").read_text(encoding="utf-8"))
    sets = {s["id"]: s for s in cat["sets"]}
    for sid in ("research-feed", "research-answer-key"):
        s = sets.get(sid)
        results.append((f"catalog {sid}", bool(s) and all(list(PRACTICE.parent.glob(f)) for f in s["files"]), str(s)[:200]))
    bad = [x for x in results if not x[1]]
    for name, ok, why in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f" — {why}"))
    if bad:
        print(f"RESEARCH PRACTICE FAILED ({len(bad)}/{len(results)})")
        return 1
    print(f"RESEARCH PRACTICE OK — {len(results)}개 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
