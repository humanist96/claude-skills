"""수집·집계 결과를 마크다운 다이제스트로 쓴다. 해석·전망은 넣지 않는다(사람이나 Claude가 이 다이제스트를 읽고 판단한다)."""
from __future__ import annotations

from pathlib import Path


def generate(collected: dict, analysis: dict, cfg: dict, out_dir: str = "reports") -> Path:
    kw = ", ".join(cfg.get("keywords") or [])
    day = collected["collected_at"][:10]
    lines = [f"# {kw} 뉴스 다이제스트 ({day})", "",
             f"> 수집 시각 {collected['collected_at']} · 기간 {collected['since']} 이후 · 기사 {analysis['count']}건", ""]
    if analysis["count"] < 3:
        lines += ["기사가 3건 미만이다. 키워드나 기간(config.yaml의 window_days)을 넓혀 본다.", ""]
    if analysis["top_terms"]:
        lines += ["## 많이 나온 단어(언급 기사 수)", "", ", ".join(f"{t['term']} {t['articles']}" for t in analysis["top_terms"]), ""]
    lines += ["## 기사 목록", "", "| 날짜 | 제목 | 매체 |", "|------|------|------|"]
    for it in collected["items"][: int(cfg.get("max_items", 30))]:
        title = it["title"].replace("|", "/")
        link = f"[{title}]({it['url']})" if it["url"] else title
        lines.append(f"| {it['published'] or '-'} | {link} | {it['publisher']} |")
    lines += ["", "## 수집 상태", ""] + [f"- {f['feed']}: {f['status']} ({f['items']}건)" for f in collected["feeds"]]
    lines += ["", "*자동 수집한 기사 목록이다. 내용의 정확성은 각 기사 원문에서 확인한다. 투자 조언이 아니다.*", ""]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in (cfg.get("keywords") or ["report"])[0])[:30]
    path = out / f"{safe}_{day}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
