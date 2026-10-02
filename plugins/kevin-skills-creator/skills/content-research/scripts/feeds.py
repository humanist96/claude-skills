#!/usr/bin/env python3
"""분야(책 7장의 `/content-research tech` 인자 포함)에 맞는 뉴스 피드와 검색어를 낸다.

피드는 2026-10-02에 실제로 접속해 응답을 확인한 것만 둔다. 키워드마다 구글 뉴스(한국어) 피드를 더한다.
맞춤 피드는 오버라이드 폴더의 references/feeds.md(표: | 분야 | 이름 | 주소 |)로 더한다.

사용법: python feeds.py [분야] [--keyword "AI 에이전트"] [--days 7] [--today 2026-10-02] [--json]
마지막 줄: FEEDS <분야> feeds=N queries=N
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
sys.path.insert(0, str(HERE / "_vendor"))

# 분야 별칭(책 7장·v1.6.1 인자 호환): tech, korean-it, cooking, finance, travel
ALIASES = {
    "tech": ["tech", "테크", "ai", "인공지능", "it", "테크/ai", "기술", "개발"],
    "korean-it": ["korean-it", "한국it", "한국 it", "국내 it", "스타트업"],
    "cooking": ["cooking", "food", "요리", "음식", "레시피", "식품"],
    "finance": ["finance", "금융", "경제", "주식", "재테크", "투자"],
    "travel": ["travel", "여행", "관광"],
    "beauty": ["beauty", "뷰티", "화장품", "스킨케어"],
    "game": ["game", "게임", "게이밍"],
}
FEEDS = {
    "tech": [("GeekNews", "https://news.hada.io/rss"), ("요즘IT", "https://yozm.wishket.com/magazine/feed/"),
             ("TechCrunch", "https://techcrunch.com/feed/"), ("The Verge", "https://www.theverge.com/rss/index.xml")],
    "korean-it": [("GeekNews", "https://news.hada.io/rss"), ("요즘IT", "https://yozm.wishket.com/magazine/feed/")],
    "cooking": [("Bon Appetit", "https://www.bonappetit.com/feed/rss")],
    "finance": [("한국경제", "https://www.hankyung.com/feed/all-news"), ("매일경제", "https://www.mk.co.kr/rss/30000001/")],
    "travel": [],
    "beauty": [("Allure", "https://www.allure.com/feed/rss")],
    "game": [("IGN", "https://feeds.feedburner.com/ign/all")],
}
DEFAULT_KEYWORDS = {"tech": "AI", "korean-it": "IT 스타트업", "cooking": "요리 트렌드", "finance": "경제 이슈", "travel": "여행 트렌드",
                    "beauty": "뷰티 트렌드", "game": "게임 신작", "general": "트렌드"}
QUERIES = ["{kw} 이번 주", "{kw} 출시 발표 {year}", "{kw} 화제", "{kw} 조사 결과"]
GOOGLE_NEWS = "https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"


def category(text: str | None) -> str:
    t = (text or "").strip().lower()
    for cat, names in ALIASES.items():
        if t == cat or t in names or any(n in t for n in names if len(n) >= 2):
            return cat
    return "general"


def custom_feeds(cat: str) -> list[tuple[str, str]]:
    try:
        from overrides import resolve  # type: ignore
        hit = resolve("content-research", "references/feeds.md", SKILL_DIR)
    except ImportError:
        return []
    if not hit.get("path"):
        return []
    out = []
    for line in Path(hit["path"]).read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[2].startswith("http") and category(cells[0]) in (cat, "general"):
            out.append((cells[1], cells[2]))
    return out


def plan(cat: str, keyword: str | None, days: int, today: date) -> dict:
    kw = keyword or DEFAULT_KEYWORDS.get(cat, "트렌드")
    feeds = [{"name": f"Google 뉴스: {kw}", "url": GOOGLE_NEWS.format(q=quote_plus(f"{kw} when:{days}d"))}]
    feeds += [{"name": n, "url": u} for n, u in custom_feeds(cat) + FEEDS.get(cat, [])]
    return {"category": cat, "keyword": kw, "days": days, "feeds": feeds,
            "queries": [q.format(kw=kw, year=today.year) for q in QUERIES]}


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="분야별 피드·검색어")
    ap.add_argument("field", nargs="?")
    ap.add_argument("--keyword")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--today")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    today = date.fromisoformat(a.today) if a.today else date.today()
    cat = category(a.field)
    keyword = a.keyword or (a.field if a.field and cat == "general" else None)
    p = plan(cat, keyword, a.days, today)
    if a.json:
        print(json.dumps(p, ensure_ascii=False, indent=2))
    else:
        print(f"분야: {cat} · 키워드: {p['keyword']} · 최근 {a.days}일")
        for f in p["feeds"]:
            print(f"피드: {f['name']} {f['url']}")
        print("검색어: " + " / ".join(p["queries"]))
    print(f"FEEDS {cat} feeds={len(p['feeds'])} queries={len(p['queries'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
