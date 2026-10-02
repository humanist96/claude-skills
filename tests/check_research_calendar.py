#!/usr/bin/env python3
"""R4: calendar_slots.py가 발행 날짜 칸을 정확히 만들고(요일·지난 날짜·칸 수) 잘못된 입력을 거부하는지 확인한다.
정답은 datetime으로 따로 계산해 비교한다."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _research_fixtures import KEY, run_script  # noqa: E402

results: list[tuple[str, bool, str]] = []


def oracle(start: date, weeks: int, wd: list[int], today: date) -> list[str]:
    mon = start - timedelta(days=start.weekday())
    return [d.isoformat() for w in range(weeks) for d in (mon + timedelta(weeks=w, days=x) for x in wd) if d >= start and d >= today]


def slots(*args) -> tuple[list, str]:
    r = run_script("calendar_slots.py", *args, "--json")
    try:
        return json.loads(r.stdout[: r.stdout.rindex("CALENDAR")]), r.stdout.strip().splitlines()[-1]
    except ValueError:
        return [], r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    cal = KEY["calendar_eval"]
    rows, last = slots("--start", cal["start"], "--weeks", cal["weeks"], "--per-week", cal["per_week"], "--days", ",".join(cal["weekdays"]),
                       "--today", KEY["as_of"])
    dates = [r["date"] for r in rows]
    results.append(("책 7장 캘린더: 12주 주 2회 화·금 = 24칸", len(rows) == cal["slots"] and dates[0] == cal["first"] and dates[-1] == cal["last"], last))
    results.append(("datetime 정답과 같다", dates == oracle(date(2026, 10, 6), 12, [1, 4], date(2026, 10, 2)), ""))
    results.append(("요일 표기가 맞다", all("월화수목금토일"[date.fromisoformat(r["date"]).weekday()] == r["weekday"] for r in rows), ""))
    rows2, _ = slots("--start", "2026-10-06", "--weeks", "4", "--per-week", "3", "--today", "2026-10-02")
    results.append(("기본 요일(주 3회 = 월·수·금), 시작일 이전 칸 제외", [r["date"] for r in rows2] == oracle(date(2026, 10, 6), 4, [0, 2, 4], date(2026, 10, 2)),
                    str([r["date"] for r in rows2][:3])))
    rows3, _ = slots("--start", "2026-10-07", "--weeks", "1", "--per-week", "2", "--days", "mon,thu", "--today", "2026-10-02")
    results.append(("영문 요일, 첫 주 지난 요일 제외", [r["date"] for r in rows3] == ["2026-10-08"], str(rows3)))
    rows4, last4 = slots("--today", "2026-10-02", "--weeks", "2", "--per-week", "1")
    results.append(("시작일 생략 = 다음 월요일 주", [r["date"] for r in rows4] == ["2026-10-06", "2026-10-13"], last4))
    for name, args in (("지난 시작일 거부", ["--start", "2026-09-01", "--today", "2026-10-02"]),
                       ("요일 수와 주당 횟수 불일치 거부", ["--start", "2026-10-06", "--per-week", "2", "--days", "화", "--today", "2026-10-02"]),
                       ("알 수 없는 요일 거부", ["--start", "2026-10-06", "--per-week", "1", "--days", "화요일x", "--today", "2026-10-02"]),
                       ("주당 8회 거부", ["--start", "2026-10-06", "--per-week", "8", "--today", "2026-10-02"])):
        _, l = slots(*args)
        results.append((name, l.startswith("CALENDAR ERROR"), l))
    bad = [x for x in results if not x[1]]
    for name, ok, why in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f" — {why}"))
    if bad:
        print(f"RESEARCH CALENDAR FAILED ({len(bad)}/{len(results)})")
        return 1
    print(f"RESEARCH CALENDAR OK — {len(results)}개 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
