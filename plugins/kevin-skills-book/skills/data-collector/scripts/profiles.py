#!/usr/bin/env python3
"""키워드에 맞는 도메인 프로필을 고르고 리서치 플랜 재료(검색어·뉴스 피드·연관 키워드·분석 틀)를 낸다.

프로필 위치(같은 파일 이름이면 앞의 것이 이긴다)
  <작업 폴더>/.claude/claude-skills/data-collector/domain_profiles/  ← 팀 맞춤
  ~/.claude/claude-skills/data-collector/domain_profiles/            ← 개인 맞춤
  <스킬 폴더>/domain_profiles/                                        ← 기본 6종
맞는 프로필이 없으면 general(웹 검색·구글 뉴스 중심)로 동작한다.

사용법: python profiles.py "<키워드>" [--domain food] [--today 2026-10-02] [--json]
마지막 줄: PROFILE <domain> queries=N feeds=N
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
sys.path.insert(0, str(HERE / "_vendor"))

GOOGLE_NEWS_KO = "https://news.google.com/rss/search?q={keyword}&hl=ko&gl=KR&ceid=KR:ko"
DISCLAIMER_DOMAINS = {"finance", "realestate"}
GENERAL = {
    "domain": "general", "display_name": "일반",
    "sources": {"free": [
        {"type": "rss", "name": "Google 뉴스(한국어)", "url": GOOGLE_NEWS_KO},
        {"type": "web_search", "name": "최근 동향", "query_template": "{keyword} 동향 {year}"},
        {"type": "web_search", "name": "전망", "query_template": "{keyword} 전망 {year}"},
        {"type": "web_search", "name": "통계·시장 규모", "query_template": "{keyword} 시장 규모 통계"},
    ]},
    "analysis": {"framework": [{"name": "주요 사건·발표"}, {"name": "수치 변화"}, {"name": "주요 플레이어"}, {"name": "리스크·불확실성"}]},
}


def _yaml():
    try:
        import yaml  # type: ignore
        return yaml
    except ImportError:
        sys.exit("pyyaml이 필요하다: pip install pyyaml")


def profile_dirs(project_dir=None, home=None) -> list[Path]:
    try:
        from overrides import roots  # type: ignore
        return [base / "domain_profiles" for _, base in roots("data-collector", SKILL_DIR, project_dir, home)]
    except ImportError:
        return [SKILL_DIR / "domain_profiles"]


def load_profiles(project_dir=None, home=None) -> dict[str, dict]:
    y = _yaml()
    out: dict[str, dict] = {}
    for d in profile_dirs(project_dir, home):
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.y*ml")):
            if f.stem in out:
                continue
            data = y.safe_load(f.read_text(encoding="utf-8")) or {}
            data.setdefault("domain", f.stem)
            data["_path"] = str(f)
            out[f.stem] = data
    return out


def detect(keyword: str, profiles: dict[str, dict]) -> tuple[str, int]:
    k = keyword.lower()
    best, score = "general", 0
    for name, p in profiles.items():
        s = sum(1 for w in p.get("keywords", []) if str(w).lower() in k or (len(str(w)) >= 2 and k in str(w).lower()))
        if s > score:
            best, score = name, s
    return best, score


def season(today: date) -> str:
    return {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
            6: "summer", 7: "summer", 8: "summer"}.get(today.month, "autumn")


def plan(keyword: str, prof: dict, today: date) -> dict:
    queries, feeds = [], []
    for s in (prof.get("sources", {}) or {}).get("free", []) or []:
        if s.get("type") == "web_search" and s.get("query_template"):
            queries.append({"name": s.get("name", ""), "query": s["query_template"].format(keyword=keyword, year=today.year)})
        elif s.get("type") == "rss":
            url = s.get("url", "")
            feeds.append({"name": s.get("name", ""), "url": url.replace("{keyword}", quote_plus(keyword))})
    if not any("news.google.com" in f["url"] for f in feeds):
        feeds.insert(0, {"name": "Google 뉴스(한국어)", "url": GOOGLE_NEWS_KO.replace("{keyword}", quote_plus(keyword))})
    expansion = []
    for rule in (prof.get("keyword_expansion", {}) or {}).get("rules", []) or []:
        for key, words in (rule.get("examples") or {}).items():
            if key in keyword or keyword in key:
                expansion += list(words)
        if rule.get("type") == "seasonal":
            expansion += list((rule.get("mapping") or {}).get(season(today), []))
    paid = [{"name": s.get("name", ""), "env": str(s.get("requires_key", "")).upper() + "_KEY"}
            for s in (prof.get("sources", {}) or {}).get("paid", []) or []]
    return {
        "keyword": keyword, "domain": prof.get("domain", "general"), "display_name": prof.get("display_name", ""),
        "queries": queries, "feeds": feeds, "expansion": list(dict.fromkeys(expansion))[:12],
        "framework": [f.get("name", "") for f in (prof.get("analysis", {}) or {}).get("framework", [])],
        "highlight_sections": (prof.get("report", {}) or {}).get("highlight_sections", []),
        "disclaimer_required": prof.get("domain") in DISCLAIMER_DOMAINS, "paid_sources": paid,
    }


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="도메인 프로필 → 리서치 플랜 재료")
    ap.add_argument("keyword")
    ap.add_argument("--domain")
    ap.add_argument("--today")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    today = date.fromisoformat(a.today) if a.today else date.today()
    profs = load_profiles()
    name = a.domain or detect(a.keyword, profs)[0]
    prof = profs.get(name, GENERAL)
    p = plan(a.keyword, prof, today)
    if a.json:
        print(json.dumps(p, ensure_ascii=False, indent=2))
    else:
        print(f"도메인: {p['domain']} {p['display_name']}" + (f" ({prof.get('_path')})" if prof.get("_path") else ""))
        print("검색어: " + " / ".join(q["query"] for q in p["queries"]))
        print("뉴스 피드: " + " / ".join(f"{f['name']} {f['url']}" for f in p["feeds"]))
        if p["expansion"]:
            print("연관 키워드: " + ", ".join(p["expansion"]))
        if p["framework"]:
            print("분석 틀: " + ", ".join(p["framework"]))
        if p["disclaimer_required"]:
            print("주의: 금융·부동산 — 투자 권유 금지, 보고서 끝에 '투자 조언이 아니다' 고지")
        if p["paid_sources"]:
            print("유료 API(환경변수에 키가 있을 때만): " + ", ".join(f"{s['name']}({s['env']})" for s in p["paid_sources"]))
    print(f"PROFILE {p['domain']} queries={len(p['queries'])} feeds={len(p['feeds'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
