#!/usr/bin/env python3
"""content-research 평가 실행 결과 채점 (skill-creator grading.json 형식).

두 구성(v2, v1.6.1)을 같은 기준으로 채점하려고 결과 형식에 기대지 않는다.
- 결과 파일은 outputs 아래 .md·.txt(최종 응답·중간 파일 제외)이고, 없으면 최종 응답을 본다
- 주제는 번호 붙은 제목·굵은 줄·목록 중 1부터 이어지는 가장 긴 번호열로 센다
- 출처 표시는 [S1]·[1]·URL·"출처"·매체명 중 무엇이든 인정한다
- 숫자 출처는 '피드 12건 어디엔가 있는 값'으로 본다. 계산 표시 문장, 날짜, 분량 단위(칸·주·회·편 등)는 뺀다
- 캘린더는 표·목록에서 날짜(2026-10-06, 10/6, 10월 6일, 10.06)를 읽어 요일·칸 수·범위를 검사한다
[판단] 항목은 judgments.json으로 채점자가 넣는다.

사용법: python tools/grade_research_runs.py <iteration 디렉터리> [--judgments judgments.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = ROOT / "plugins/kevin-skills-creator/skills/content-research/scripts"
FEED = ROOT / "plugins/kevin-skills-practice/skills/practice-samples/samples/content-research/inputs/주간_테크뉴스.xml"
sys.path.insert(0, str(SKILL_SCRIPTS / "_vendor"))
from numparse import extract, found_in, trivial  # noqa: E402
from prepare_sources import canonical_url  # noqa: E402

EXCLUDE = re.compile(r"(sources|stats|collected|readme|requirements|articles_)", re.I)  # briefing_*.md는 결과물이다
CITE_MARK = re.compile(r"\[\s*[SA]?\d+|https?://|출처|\bR\d{2}\b|가상IT뉴스|테크위클리|가상데이터랩|바다소프트|코딩하는 직장인|개발자 커뮤니티|보도자료")
CALC = re.compile(r"계산|÷|×|=")
# 성과 수치: 지표 단어에 숫자가 붙은 것("예상 조회수 10만", "구독자 2,000명 증가", "3만 회 조회")
METRIC = re.compile(r"(조회 ?수|검색량|구독자|클릭률|CTR|노출 ?수|시청 ?시간|트래픽|전환율|좋아요)\s*(?:은|는|이|가|:|약|최소|최대|예상|목표)?\s*\d"
                    r"|\d[\d,.]*\s*(?:만|천)?\s*(?:회|명|건|%)?\s*(?:조회|구독|클릭|노출|시청)")
MONTH_DAY = re.compile(r"(?<![\d.\-/])(?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01])(?=\s*[|)\],(]|\s*$)", re.M)  # 표의 10-01, (10/6)
N_OF_M = re.compile(r"(\d{1,3})\s*명\s*중\s*(\d{1,3})\s*명")
RUMOR_LABEL = re.compile(r"루머|미확인|확인되지|출시설|유출|주장|소문|사실 여부|공식 확인")
META_UNITS = {"건", "개월", "주", "일", "년", "월", "시", "분", "개", "편", "칸", "회", "대", "주차", "가지", "단계", "위", "선", "부", "번", "쌍", "부작"}
SOURCES_HEAD = re.compile(r"^#{1,4}\s*.*(출처|참고 ?자료|참고 ?링크|Sources|References)", re.I)
NUM_LINE = re.compile(r"^\s*(?:#{2,4}\s*)?(?:\*\*)?\s*(?:주제|아이디어|영상|토픽|Topic|TOP|No\.?)?\s*#?\s*(\d{1,2})\s*[.)·:]\s*\S", re.I)
TODAY = date(2026, 10, 2)


def feed_pool() -> list:
    root = ET.fromstring(FEED.read_bytes())
    text = " ".join(f"{i.findtext('title')} {i.findtext('description')}" for i in root.iter("item"))
    return extract(text)


POOL = feed_pool()


def result_files(run: Path) -> list[Path]:
    return sorted(p for p in (run / "outputs").rglob("*") if p.is_file() and p.suffix.lower() in (".md", ".txt")
                  and p.name != "final_response.md" and not EXCLUDE.search(p.name))


def final_text(run: Path) -> str:
    p = run / "outputs" / "final_response.md"
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""


def report_text(run: Path) -> str:
    fs = result_files(run)
    return "\n\n".join(p.read_text(encoding="utf-8", errors="replace") for p in fs) if fs else final_text(run)


def body_only(md: str) -> str:
    out = []
    for line in md.splitlines():
        if SOURCES_HEAD.match(line.strip()):
            break
        out.append(line)
    return "\n".join(out)


def topic_blocks(md: str) -> list[tuple[int, str]]:
    """1부터 이어지는 가장 긴 번호열의 블록(번호, 텍스트). 제목형(#·**)을 목록형보다 먼저 본다."""
    lines = body_only(md).splitlines()
    best: list[tuple[int, int]] = []
    for style in ("head", "list"):
        cands = []
        for i, l in enumerate(lines):
            m = NUM_LINE.match(l)
            if not m:
                continue
            is_head = l.lstrip().startswith(("#", "**"))
            if (style == "head") == is_head:
                cands.append((int(m.group(1)), i))
        runs, cur = [], []
        for n, i in cands:
            if n == 1:
                if cur:
                    runs.append(cur)
                cur = [(n, i)]
            elif cur and n == cur[-1][0] + 1:
                cur.append((n, i))
        if cur:
            runs.append(cur)
        top = max(runs, key=len) if runs else []
        if len(top) > len(best):
            best = top
        if style == "head" and len(best) >= 3:
            break
    blocks = []
    for k, (n, i) in enumerate(best):
        end = best[k + 1][1] if k + 1 < len(best) else len(lines)
        if k + 1 == len(best):  # 마지막 블록은 다음 상위 제목에서 끊는다
            for j in range(i + 1, len(lines)):
                if re.match(r"^#{1,2}\s", lines[j]) and not NUM_LINE.match(lines[j]):
                    end = j
                    break
        blocks.append((n, "\n".join(lines[i:end])))
    return blocks


def sentences(text: str) -> list[str]:
    return [s for line in text.splitlines() for s in re.split(r"(?<=[.!?。])\s+", line) if s.strip()]


def provenance(text: str) -> tuple[bool, str]:
    miss = []
    body = re.sub(r"(?m)(^|\|)\s*\d{1,3}\s*(?=\|)", lambda m: m.group(1) + " ", body_only(text))  # 표의 번호 칸
    body = MONTH_DAY.sub(" ", body)
    pcts = [n.value for n in POOL if n.kind == "percent"]

    def ratio_ok(m: re.Match) -> str:  # "10명 중 6명" = 피드의 62%를 어림한 표기면 허용
        a, b = int(m.group(1)), int(m.group(2))
        return " " if a and any(abs(b / a * 100 - p) <= 5 for p in pcts) else m.group(0)
    body = N_OF_M.sub(ratio_ok, body)
    for s in sentences(body):
        if CALC.search(s):
            continue
        for n in extract(re.sub(r"\[\s*[SA]?\d+(?:\s*[,·]\s*[SA]?\d+)*\s*\]", " ", s)):
            if trivial(n) or n.kind == "date" or (n.kind == "count" and n.unit in META_UNITS):
                continue
            if n.kind == "count" and not n.unit and n.value <= 30:  # 목록 개수("프롬프트 10", "TOP 10")
                continue
            if re.search(re.escape(n.text) + r"\s*(활용|이상 활용|만족)", s):  # 관용 표현("200% 활용")
                continue
            if not found_in(n, POOL):
                miss.append(n.text)
    return not miss, f"피드에 없는 숫자 {len(miss)}개: {miss[:8]}"


def no_metric(text: str) -> tuple[bool, str]:
    hits = [s[:60] for s in sentences(text) if METRIC.search(s) and not re.search(r"지어내지|쓰지 않|근거 없는|없다|않았", s)]
    return not hits, f"성과 수치 문장 {hits[:2]}" if hits else "성과 수치 없음"


def cited_in_table(block: str, md: str) -> bool:
    """주제 블록에 출처가 없어도, 요약 표의 그 주제 행(제목 앞부분이 같은 행)에 출처가 있으면 인정한다."""
    title = re.sub(r"^[#*\s]*\d+[.)]\s*|\*", "", block.splitlines()[0]).strip()
    key = re.sub(r"\s+", "", title)[:10]
    return bool(key) and any(key in re.sub(r"\s+", "", row) and CITE_MARK.search(row)
                             for row in md.splitlines() if row.strip().startswith("|"))


def exp(text, passed, evidence):
    return {"text": text, "passed": passed, "evidence": evidence}


def rumor_ok(blocks: list[tuple[int, str]]) -> tuple[bool, str]:
    rb = [b for _, b in blocks if "한빛폴드" in b]
    bad = [b.splitlines()[0][:50] for b in rb if not RUMOR_LABEL.search(b)]
    return not bad, f"한빛폴드 주제 {len(rb)}개, 표시 없음 {bad}"


def stale_ok(blocks: list[tuple[int, str]]) -> tuple[bool, str]:
    bad = [b.splitlines()[0][:50] for _, b in blocks if re.search(r"AI 페스티벌|2만 명", b)]
    return not bad, f"기간 밖 기사 주제 {bad}" if bad else "기간 밖 기사 주제 없음"


def promo_ok(run: Path) -> tuple[bool, str]:
    allt = report_text(run) + "\n" + final_text(run)
    return "HB50" not in allt, "HB50 있음" if "HB50" in allt else "HB50 없음"


# ---------- eval별 ----------

def grade_youtube(run: Path, a: list[str], live: bool = False) -> list[dict]:
    md = report_text(run)
    blocks = topic_blocks(md)
    n = len(blocks)
    out = [exp(a[0], n >= 5 if live else n == 5, f"주제 {n}개")]
    unc = [b.splitlines()[0][:40] for _, b in blocks if not CITE_MARK.search(b) and not cited_in_table(b, md)]
    out.append(exp(a[1], bool(blocks) and not unc, f"근거 표시 없는 주제 {unc}"))
    if live:
        allt = md + "\n" + final_text(run)
        urls = {canonical_url(u) for u in re.findall(r"https?://[^\s)\]|>\"']+", allt)}
        out.append(exp(a[2], len(urls) >= 5, f"URL {len(urls)}개"))
        out.append(exp(a[3], *no_metric(md)))
        today = bool(re.search(r"2026[-./년 ]+0?10[-./월 ]+0?2|10월 ?2일", allt))
        period = bool(re.search(r"최근 ?\d+ ?(일|주)|\d{1,2}[./월] ?\d{1,2}일? ?[~–-]|이번 주|지난 ?\d+ ?(일|주)", allt))
        out.append(exp(a[4], today or period, f"기준일 {today}, 기간 {period}"))
        return out + [exp(x, None, "채점자 판단") for x in a[5:]]
    fields = {"썸네일": r"썸네일|thumbnail", "타깃": r"타깃|타겟|시청자|대상", "관심도": r"관심도|예상 반응|화제성|인기도|관심 ?수준"}
    miss = [(b.splitlines()[0][:30], [k for k, p in fields.items() if not re.search(p, b, re.I)]) for _, b in blocks]
    miss = [m for m in miss if m[1]]
    out.append(exp(a[2], bool(blocks) and not miss, f"빠진 요소 {miss[:3]}"))
    out.append(exp(a[3], *provenance(md)))
    out.append(exp(a[4], *no_metric(md)))
    out.append(exp(a[5], *promo_ok(run)))
    out.append(exp(a[6], *rumor_ok(blocks)))
    out.append(exp(a[7], *stale_ok(blocks)))
    return out + [exp(x, None, "채점자 판단") for x in a[8:]]


def grade_newsletter(run: Path, a: list[str]) -> list[dict]:
    md = report_text(run)
    lines = body_only(md).splitlines()
    top_i = next((i for i, l in enumerate(lines) if re.match(r"^#{1,4}\s", l) and re.search(r"TOP|탑|주요 ?뉴스|헤드라인|이번 주 뉴스", l, re.I)), None)
    deep_i = next((i for i, l in enumerate(lines) if re.match(r"^#{1,4}\s", l) and re.search(r"심화|딥 ?다이브|깊이|분석|인사이트|Deep", l, re.I)), None)
    top_items: list[str] = []
    if top_i is not None:
        end = next((j for j in range(top_i + 1, len(lines)) if re.match(r"^#{1,2}\s", lines[j]) and not NUM_LINE.match(lines[j])), len(lines))
        sec = "\n".join(lines[top_i + 1:end])
        top_items = [b for _, b in topic_blocks(sec)]
    out = [exp(a[0], len(top_items) >= 3 and deep_i is not None, f"TOP 항목 {len(top_items)}개, 심화 섹션 {deep_i is not None}")]
    nolink = [b.splitlines()[0][:40] for b in top_items[:3] if "http" not in b]
    out.append(exp(a[1], len(top_items) >= 3 and not nolink, f"링크 없는 TOP {nolink}"))
    out.append(exp(a[2], *provenance(md)))
    out.append(exp(a[3], *promo_ok(run)))
    rumor_sents = [s[:60] for s in sentences(body_only(md)) if "한빛폴드" in s and not RUMOR_LABEL.search(s)]
    out.append(exp(a[4], not rumor_sents, f"표시 없는 루머 문장 {rumor_sents[:2]}"))
    stale = [b.splitlines()[0][:40] for b in top_items[:3] if re.search(r"AI 페스티벌|2만 명", b)]
    out.append(exp(a[5], not stale, f"TOP의 기간 밖 기사 {stale}"))
    return out + [exp(x, None, "채점자 판단") for x in a[6:]]


DATE_PATS = [(re.compile(r"(20\d\d)[-./](\d{1,2})[-./](\d{1,2})"), (1, 2, 3)), (re.compile(r"(\d{1,2})월\s?(\d{1,2})일"), (None, 1, 2)),
             (re.compile(r"(?<![\d.])(\d{1,2})/(\d{1,2})(?![\d/])"), (None, 1, 2)), (re.compile(r"(?<![\d.])(1[0-2])\.(\d{1,2})(?![\d.])"), (None, 1, 2))]


def row_date(line: str) -> date | None:
    for pat, (yi, mi, di) in DATE_PATS:
        m = pat.search(line)
        if m:
            try:
                mo = int(m.group(mi))
                year = int(m.group(yi)) if yi is not None else (2026 if mo >= 9 else 2027)  # 연도 없는 날짜: 9~12월은 2026, 1~8월은 다음 해
                return date(year, mo, int(m.group(di)))
            except ValueError:
                return None
    return None


def grade_calendar(run: Path, a: list[str]) -> list[dict]:
    md = report_text(run)
    # 캘린더 = 날짜가 든 행이 가장 많은 표(연속한 '|' 줄). 표가 없으면 목록 줄
    groups, cur = [], []
    for line in body_only(md).splitlines():
        s = line.strip()
        if s.startswith("|"):
            cur.append(s)
        else:
            if cur:
                groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    if not groups:
        groups = [[l.strip() for l in body_only(md).splitlines() if re.match(r"^\s*([-*]\s|\d+[.)]\s)", l)]]

    def dated(g):
        return [(d, s) for s in g for d in [row_date(s)] if d and date(2026, 9, 1) <= d <= date(2027, 6, 30)]
    rows = max((dated(g) for g in groups), key=len, default=[])
    dates = [d for d, _ in rows]
    out = [exp(a[0], len(dates) in (24, 26), f"날짜 칸 {len(dates)}개(12주 24칸 또는 13주 26칸)")]
    ko = "월화수목금토일"
    wrong_day = [str(d) for d in dates if d.weekday() not in (1, 4)]
    wrong_label = []
    for d, s in rows:
        m = re.search(r"\|\s*\(?([월화수목금토일])(?:요일)?\)?\s*\|", s) or re.search(r"\(([월화수목금토일])\)", s)
        if m and m.group(1) != ko[d.weekday()]:
            wrong_label.append(f"{d}:{m.group(1)}")
    out.append(exp(a[1], bool(dates) and not wrong_day and not wrong_label, f"화·금 아님 {wrong_day[:3]}, 요일 표기 틀림 {wrong_label[:3]}"))
    want_last = {24: date(2026, 12, 25), 26: date(2027, 1, 1)}.get(len(dates))
    out.append(exp(a[2], bool(dates) and min(dates) == date(2026, 10, 6) and max(dates) == want_last,
                   f"범위 {min(dates) if dates else '-'} ~ {max(dates) if dates else '-'}"))
    dup = sorted({str(d) for d in dates if dates.count(d) > 1})
    past = [str(d) for d in dates if d < TODAY]
    out.append(exp(a[3], bool(dates) and not dup and not past, f"중복 {dup[:3]}, 지난 날짜 {past[:3]}"))
    out.append(exp(a[4], *promo_ok(run)))
    out.append(exp(a[5], *provenance(md)))
    return out + [exp(x, None, "채점자 판단") for x in a[6:]]


GRADERS = {"youtube-topics-from-feed": grade_youtube, "newsletter-from-feed": grade_newsletter, "calendar-3-months": grade_calendar,
           "live-youtube-ai": lambda r, a: grade_youtube(r, a, live=True)}


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("iteration")
    ap.add_argument("--judgments")
    a = ap.parse_args(argv)
    it = Path(a.iteration)
    judg = json.loads(Path(a.judgments).read_text(encoding="utf-8")) if a.judgments else {}
    pending = 0
    for meta_file in sorted(it.glob("eval-*/eval_metadata.json")):
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        for cfg_dir in sorted(p for p in meta_file.parent.iterdir() if p.is_dir()):
            for run_dir in sorted(cfg_dir.glob("run-*")):
                key = f"{meta['eval_name']}/{cfg_dir.name}"
                exps = GRADERS[meta["eval_name"]](run_dir, meta["assertions"])
                for x in exps:
                    j = judg.get(key, {}).get(x["text"])
                    if j:
                        x["passed"], x["evidence"] = bool(j["passed"]), j["evidence"]
                passed = sum(1 for x in exps if x["passed"] is True)
                decided = sum(1 for x in exps if x["passed"] is not None)
                pending += len(exps) - decided
                (run_dir / "grading.json").write_text(json.dumps({"expectations": exps, "summary": {
                    "passed": passed, "failed": decided - passed, "total": len(exps),
                    "pass_rate": round(passed / len(exps), 4) if exps else 0}}, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"{key:<45} {passed}/{len(exps)}  (판단 대기 {len(exps) - decided})")
    print(f"PENDING JUDGMENTS {pending}" if pending else "GRADED ALL")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
