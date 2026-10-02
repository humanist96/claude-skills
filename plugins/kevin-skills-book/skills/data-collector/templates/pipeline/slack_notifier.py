"""Slack Incoming Webhook으로 새 기사 목록과 요약을 보낸다.

웹훅 주소는 환경변수 SLACK_WEBHOOK_URL을 먼저 읽고, 없으면 config.yaml의 slack.webhook_url을 쓴다.
GitHub Actions에서는 Secrets에 넣어 환경변수로 전달한다. config.yaml에 주소를 적어 커밋하면 주소가 공개된다.
SLACK_DRY_RUN=1이면 보내지 않고 메시지를 화면에 출력한다.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import date, timedelta


def format_message(items: list[dict], analysis: dict, cfg: dict, report_path: str, today: date | None = None) -> str:
    sc = cfg.get("slack") or {}
    today = today or date.today()
    since = (today - timedelta(days=int(sc.get("new_days", 1)))).isoformat()
    new = [it for it in items if it.get("published") and it["published"] >= since][: int(sc.get("max_headlines", 10))]
    kw = ", ".join(cfg.get("keywords") or [])
    lines = [f"*{kw}* 뉴스 ({today.isoformat()}) — 새 기사 {len(new)}건 / 기간 내 {analysis['count']}건"]
    if new:
        for it in new:
            title = it["title"].replace("<", "‹").replace(">", "›")
            lines.append(f"• <{it['url']}|{title}> — {it['publisher']}" if it.get("url") else f"• {title} — {it['publisher']}")
    else:
        lines.append("새 기사가 없다.")
    terms = ", ".join(t["term"] for t in analysis["top_terms"][:5])
    if terms:
        lines.append(f"많이 나온 단어: {terms}")
    lines.append(f"다이제스트: {report_path}")
    return "\n".join(lines)


def send_notification(analysis: dict, report_path: str, cfg: dict, items: list[dict] | None = None) -> str:
    text = format_message(items or [], analysis, cfg, report_path)
    if os.environ.get("SLACK_DRY_RUN") == "1":
        print(text)
        return "dry-run: 보내지 않고 출력함"
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL") or (cfg.get("slack") or {}).get("webhook_url", "")
    if not webhook_url:
        return "skip: 웹훅 주소 없음(SLACK_WEBHOOK_URL)"
    if not webhook_url.startswith("https://hooks.slack.com/"):
        return "skip: Slack 웹훅 주소 형식이 아니다"
    req = urllib.request.Request(webhook_url, data=json.dumps({"text": text}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
        return f"sent: HTTP {r.status}"
