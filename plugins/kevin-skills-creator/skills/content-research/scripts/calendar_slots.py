#!/usr/bin/env python3
"""콘텐츠 캘린더의 발행 날짜 칸을 만든다. 날짜·요일 계산은 Claude가 하지 않고 이 스크립트로 한다.

예: 2026-11-02(월)이 있는 주부터 6주, 주 3회(기본 월·수·금) → 18칸, 2026-11-02 ~ 2026-12-11

사용법
  python calendar_slots.py --start 2026-11-02 --weeks 6 --per-week 3 [--days 월,수,금] [--today 2026-10-30] [--json]
  --start: 첫 주의 아무 날(그 주 월요일부터 센다). 생략하면 오늘 다음 월요일
  --days: 요일(월화수목금토일 또는 mon..sun). 생략하면 주 1회 화, 2회 화·금, 3회 월·수·금, 4회 월·화·목·금, 5회 월~금
마지막 줄: CALENDAR READY slots=N first=YYYY-MM-DD last=YYYY-MM-DD 또는 CALENDAR ERROR …
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta

KO = "월화수목금토일"
EN = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DEFAULT_DAYS = {1: [1], 2: [1, 4], 3: [0, 2, 4], 4: [0, 1, 3, 4], 5: [0, 1, 2, 3, 4], 6: [0, 1, 2, 3, 4, 5], 7: list(range(7))}


def parse_days(s: str) -> list[int]:
    out = []
    for tok in [t.strip().lower() for t in s.replace("·", ",").replace("/", ",").split(",") if t.strip()]:
        m_ko = re.fullmatch(r"([월화수목금토일])(?:요일)?", tok)
        m_en = re.fullmatch(r"(mon|tue|wed|thu|fri|sat|sun)[a-z]*", tok)
        if m_ko:
            out.append(KO.index(m_ko.group(1)))
        elif m_en:
            out.append(EN.index(m_en.group(1)))
        else:
            raise ValueError(f"요일을 알 수 없다: {tok}")
    return sorted(set(out))


def slots(start: date, weeks: int, per_week: int, days: list[int] | None, today: date) -> list[dict]:
    if weeks < 1 or per_week < 1 or per_week > 7:
        raise ValueError("주 수는 1 이상, 주당 횟수는 1~7이어야 한다")
    days = days or DEFAULT_DAYS[per_week]
    if len(days) != per_week:
        raise ValueError(f"요일 {len(days)}개와 주당 {per_week}회가 맞지 않는다")
    monday = start - timedelta(days=start.weekday())
    out = []
    for w in range(weeks):
        for d in days:
            day = monday + timedelta(weeks=w, days=d)
            if day < start or day < today:
                continue  # 시작일 이전·지난 날짜 칸은 만들지 않는다
            out.append({"no": len(out) + 1, "date": day.isoformat(), "weekday": KO[day.weekday()], "week": w + 1})
    # 시작 주에서 빠진 칸만큼 뒤에 채우지 않는다(요청한 주 수 안에서만)
    return out


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="캘린더 발행 날짜 칸")
    ap.add_argument("--start")
    ap.add_argument("--weeks", type=int, default=12)
    ap.add_argument("--per-week", type=int, default=2)
    ap.add_argument("--days")
    ap.add_argument("--today")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        today = date.fromisoformat(a.today) if a.today else date.today()
        start = date.fromisoformat(a.start) if a.start else today + timedelta(days=7 - today.weekday())
        if start < today:
            raise ValueError(f"시작일 {start}이 오늘({today})보다 앞이다")
        rows = slots(start, a.weeks, a.per_week, parse_days(a.days) if a.days else None, today)
    except ValueError as e:
        print(f"CALENDAR ERROR {e}")
        return 1
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print("| 번호 | 날짜 | 요일 | 주차 |")
        print("|---:|---|:-:|:-:|")
        for r in rows:
            print(f"| {r['no']} | {r['date']} | {r['weekday']} | {r['week']} |")
    print(f"CALENDAR READY slots={len(rows)} first={rows[0]['date'] if rows else '-'} last={rows[-1]['date'] if rows else '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
