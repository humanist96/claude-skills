"""뉴스 피드(RSS·Atom)와 선택 API에서 기사를 모아 collected.json으로 저장한다.

표준 라이브러리만 쓴다(urllib, xml.etree). 피드마다 독립적으로 수집하고 실패한 피드는 건너뛴다.
"""
from __future__ import annotations

import html
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

UA = "Mozilla/5.0 (data-collector pipeline; +https://github.com/)"
TRACKING = re.compile(r"^(utm_\w+|fbclid|gclid|ref|from|oc)$", re.I)


def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — 설정 파일의 https 피드만 연다
        return r.read()


def _text(el, *names) -> str:
    for n in names:
        x = el.find(n)
        if x is not None:
            if x.text and x.text.strip():
                return x.text.strip()
            if x.get("href"):
                return x.get("href")
    return ""


def parse_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_feed(xml: bytes, feed_name: str) -> list[dict]:
    root = ET.fromstring(xml)
    atom = "{http://www.w3.org/2005/Atom}"
    items = root.findall(".//item") or root.findall(f".//{atom}entry")
    out = []
    for it in items:
        title = _text(it, "title", f"{atom}title")
        link = _text(it, "link", f"{atom}link")
        date = _text(it, "pubDate", f"{atom}published", f"{atom}updated", "{http://purl.org/dc/elements/1.1/}date")
        desc = html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(_text(it, "description", f"{atom}summary", f"{atom}content"))))
        title = html.unescape(title)
        src = it.find("source")
        publisher = (src.text.strip() if src is not None and src.text else "") or feed_name
        out.append({"title": title, "url": link, "publisher": publisher, "published": date,
                    "text": re.sub(r"\s+", " ", desc).strip()[:600], "feed": feed_name})
    return out


def canonical(url: str) -> str:
    s = urlsplit(url)
    q = sorted((k, v) for k, v in parse_qsl(s.query) if not TRACKING.match(k))
    return urlunsplit((s.scheme, s.netloc.lower().removeprefix("www."), s.path.rstrip("/"), urlencode(q), ""))


def mentions(item: dict, keywords: list[str]) -> bool:
    text = f"{item['title']} {item['text']}".lower()
    words = {w.lower() for k in keywords for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", k)}
    return not words or any(w in text for w in words)


def feeds_from_config(cfg: dict) -> list[dict]:
    feeds = list(cfg.get("feeds") or [])
    days = int(cfg.get("window_days", 7))
    for kw in cfg.get("keywords") or []:
        if cfg.get("google_news", True):
            # when:Nd가 없으면 구글 뉴스는 관련도 순 100건을 주고 그중 최근 기사는 일부뿐이다
            feeds.append({"name": f"Google 뉴스: {kw}",
                          "url": f"https://news.google.com/rss/search?q={quote_plus(f'{kw} when:{days}d')}&hl=ko&gl=KR&ceid=KR:ko"})
    return feeds


def collect_newsapi(keywords: list[str], language: str) -> list[dict]:
    key = os.environ.get("NEWSAPI_KEY", "")
    if not key:
        return []
    out = []
    for kw in keywords:
        url = f"https://newsapi.org/v2/everything?q={quote_plus(kw)}&language={language}&sortBy=publishedAt&pageSize=20&apiKey={key}"
        try:
            data = json.loads(fetch(url))
        except Exception as e:  # noqa: BLE001
            print(f"[skip] NewsAPI {kw}: {type(e).__name__}")
            continue
        for a in data.get("articles", []):
            out.append({"title": a.get("title", ""), "url": a.get("url", ""), "publisher": (a.get("source") or {}).get("name", ""),
                        "published": a.get("publishedAt", ""), "text": a.get("description") or "", "feed": "NewsAPI"})
    return out


def run_collection(cfg: dict, offline_feed: str | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=int(cfg.get("window_days", 7)))
    items, report = [], []
    if offline_feed:
        items = parse_feed(Path(offline_feed).read_bytes(), "offline")
        report.append({"feed": offline_feed, "status": "ok", "items": len(items)})
    else:
        for f in feeds_from_config(cfg):
            try:
                got = parse_feed(fetch(f["url"]), f["name"])
                if cfg.get("filter_by_keywords", True) and "news.google.com" not in f["url"]:
                    got = [g for g in got if mentions(g, cfg.get("keywords") or [])]  # 분야 피드에서 키워드와 무관한 기사 제외
                items += got
                report.append({"feed": f["name"], "status": "ok", "items": len(got)})
            except Exception as e:  # noqa: BLE001 — 한 피드가 실패해도 계속
                report.append({"feed": f["name"], "status": f"skip: {type(e).__name__}", "items": 0})
        items += collect_newsapi(cfg.get("keywords") or [], cfg.get("language", "ko"))
    seen, kept = set(), []
    for it in items:
        d = parse_date(it["published"])
        if d and d < since:
            continue
        key = canonical(it["url"]) if it["url"] else it["title"]
        if key in seen:
            continue
        seen.add(key)
        it["published"] = d.date().isoformat() if d else ""
        kept.append(it)
    kept.sort(key=lambda x: x["published"], reverse=True)
    return {"collected_at": now.isoformat(timespec="seconds"), "since": since.date().isoformat(), "feeds": report, "items": kept}
