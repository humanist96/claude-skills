#!/usr/bin/env python3
"""콘텐츠 기획안 품질 게이트 — 사용자에게 전달하기 전에 반드시 통과시킨다.

기획안 형식(references/plan-format.md): 아이디어마다 '### 1. 제목' 블록, 근거에 [S번호], 끝에 '## 출처' 목록.

오류(전달 금지)
- uncited-idea: 출처 번호가 없는 아이디어
- unknown-citation: sources.json에 없는 번호
- stale-only: 기간 밖 소스만 근거로 든 아이디어('이번 주' 주제가 아니다)
- number-not-in-cited-source: 아이디어의 숫자가 인용한 소스에 없다(계산이면 "(계산: …)")
- unsupported-metric: 예상 조회수·검색량·구독자 증가 같은 성과 수치를 근거 없이 제시
- rumor-unlabeled: 루머·미확인 소스(커뮤니티 등)를 근거로 쓰면서 '루머·미확인'을 밝히지 않음
- duplicate-idea: 제목이 사실상 같은 아이디어
- count: 요청한 개수와 아이디어 수가 다름(--count)
- missing-field: 용도별 필수 요소 누락(--purpose youtube: 썸네일·타깃·관심도, blog: 키워드·구조, newsletter: TOP·심화)
- calendar: 캘린더 날짜가 지났거나, 요일이 요청과 다르거나, 순서가 틀리거나, 칸 수가 다름(--days, --slots)
- followed-instruction: 자료 속 지시문(FLAG)이 시킨 문구·코드를 기획안에 넣음
- sources-section: 출처 목록이 없거나 인용 번호·URL이 빠짐
- placeholder, environment-path
경고: 중복 소스 인용, 같은 단일 소스로 만든 아이디어 여러 개, 보도자료·블로그만 근거

사용법
  python verify_plan.py <plan.md> --sources sources.json [--purpose youtube|blog|newsletter|sns|general] [--count 5]
                        [--days 화,금] [--slots 24] [--today 2026-10-02] [--json]
마지막 줄: PLAN VERIFY OK 또는 PLAN VERIFY FAILED
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "_vendor"))
from numparse import extract, found_in, trivial  # noqa: E402
from prepare_sources import bigrams, containment, norm_title  # noqa: E402
from calendar_slots import parse_days  # noqa: E402

CITE = re.compile(r"\[(S\d+(?:\s*[,，·/]\s*S?\d+)*)\]")
IDEA_HEAD = re.compile(r"^###\s+(?:주제\s*)?(\d+)[.)]?\s*(.+)$")
SECTION = re.compile(r"^##\s+(.+)$")
CALC = re.compile(r"\(계산[:：][^)]*\)|\(계산\)|÷")
METRIC = re.compile(r"(조회수|조회 수|검색량|구독자|클릭률|CTR|노출 ?수|시청 ?시간|좋아요|트래픽|도달|전환율)")
RUMOR_SRC = re.compile(r"루머|유출|출시설|설\]|카더라|소문|익명")
RUMOR_LABEL = re.compile(r"루머|미확인|확인되지|출시설|유출설|주장|소문|공식 발표 전|사실 여부")
PLACEHOLDER = re.compile(r"\[(?:링크|URL|url|출처 ?필요|여기[^\]]*|TBD)\]|\bTODO\b|\bTBD\b|XXX|○○|\{\{[^}]*\}\}")
ENV = re.compile("/mnt/" + "user-data|present" + "_files")
SOURCES_HEAD = re.compile(r"^##\s*.*(출처|참고 ?자료|Sources|References)", re.I)
CAL_HEAD = re.compile(r"^##\s*.*(캘린더|일정|Calendar)", re.I)
INSTR_EXEMPT = re.compile(r"지시|무시|반영하지|따르지|홍보 문구|제외")
QUOTED = re.compile(r"['‘\"“「]([^'’\"”」]{3,60})['’\"”」]")
CODE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2,}[0-9]{1,4}(?![A-Za-z0-9])")  # 할인 코드(AB12을 — 한글 조사가 붙어도)
FACT_LINE = re.compile(r"^\s*[-*]\s*(근거|왜 지금|사실|배경)\s*[:：]")  # 숫자를 소스와 엄격히 대조하는 줄
FORMAT_UNITS = {"분", "초", "시간", "단계", "컷", "장", "일", "주", "편", "개", "가지", "선", "곡"}
L = r"[^\n:：]{0,8}[:：]"  # 라벨 뒤 콜론("썸네일:", "**썸네일 아이디어**:")
REQUIRED = {
    "youtube": [("썸네일", rf"(썸네일|thumbnail){L}"), ("타깃", rf"(타깃|타겟|시청자){L}"), ("관심도", rf"(관심도|예상 반응|화제성){L}")],
    "blog": [("키워드", rf"(키워드|keyword){L}"), ("구조", rf"(구조|소제목|목차|outline){L}")],
    "sns": [("훅", rf"(훅|첫 문장|hook){L}")],
}


def cite_ids(s: str) -> list[str]:
    out = []
    for m in CITE.finditer(s):
        for part in re.split(r"\s*[,，·/]\s*", m.group(1)):
            out.append(part if part.startswith("S") else "S" + part)
    return out


def parse(md: str) -> dict:
    ideas, section, cal_rows, src_lines, cur = [], "", [], [], None
    for line in md.splitlines():
        s = line.strip()
        sm = SECTION.match(s)
        if sm:
            section, cur = sm.group(1), None
            continue
        if SOURCES_HEAD.match("## " + section) and s:
            src_lines.append(s)
            continue
        if CAL_HEAD.match("## " + section):
            if s.startswith("|") and re.search(r"\d{4}-\d{2}-\d{2}", s):
                cal_rows.append(s)
            continue
        im = IDEA_HEAD.match(s)
        if im:
            cur = {"no": int(im.group(1)), "title": im.group(2).strip(), "section": section, "body": []}
            ideas.append(cur)
            continue
        if cur is not None:
            cur["body"].append(line)
    for i in ideas:
        i["text"] = i["title"] + "\n" + "\n".join(i["body"])
    has_sources = any(SOURCES_HEAD.match(l) for l in md.splitlines())
    return {"ideas": ideas, "calendar": cal_rows, "sources": src_lines, "has_sources": has_sources}


def verify(md: str, src: dict, purpose: str = "general", count: int | None = None, days: list[int] | None = None,
           slots: int | None = None, today: date | None = None) -> tuple[list, list, dict]:
    errs, warns = [], []
    by_id = {s["id"]: s for s in src.get("sources", [])}
    pools = {i: extract(f"{s['title']}\n{s['text']}") for i, s in by_id.items()}
    p = parse(md)
    ideas = p["ideas"]
    counted = [i for i in ideas if purpose != "newsletter" or re.search(r"TOP|탑|주요", i["section"], re.I)]
    if count is not None and len(counted) != count:
        errs.append({"check": "count", "detail": f"아이디어 {len(counted)}개(요청 {count}개)"})
    if not ideas:
        errs.append({"check": "count", "detail": "'### 1. 제목' 형식의 아이디어가 없다"})
    single_src: dict[str, list[int]] = {}
    for i in ideas:
        t, tag = i["text"], f"#{i['no']} {i['title'][:30]}"
        ids = cite_ids(t)
        if not ids:
            errs.append({"check": "uncited-idea", "detail": "출처 번호가 없다", "where": tag})
            continue
        known = [by_id[x] for x in ids if x in by_id]
        for x in ids:
            if x not in by_id:
                errs.append({"check": "unknown-citation", "detail": f"[{x}]가 sources.json에 없다", "where": tag})
        if known and all(s["status"] == "out_of_window" for s in known):
            errs.append({"check": "stale-only", "detail": f"기간 밖 소스({','.join(s['id'] for s in known)})만 근거", "where": tag})
        for s in known:
            if s["status"] == "duplicate":
                warns.append({"check": "duplicate-cited", "detail": f"{s['id']}는 {s.get('duplicate_of')}의 중복", "where": tag})
        if known and all(s["tier"] == "D" for s in known):
            warns.append({"check": "weak-source-only", "detail": "보도자료·블로그·커뮤니티만 근거", "where": tag})
        rumor = [s for s in known if RUMOR_SRC.search(s["title"]) or (s.get("kind") == "community" and s["tier"] == "D")]
        if rumor and not RUMOR_LABEL.search(t):
            errs.append({"check": "rumor-unlabeled", "detail": f"루머·미확인 소스({','.join(s['id'] for s in rumor)})인데 표시가 없다", "where": tag})
        pool = [n for s in known for n in pools[s["id"]]]
        for line in t.splitlines():
            fact_line = bool(FACT_LINE.match(line))
            for sent in re.split(r"(?<=[.!?])\s+", line):
                if CALC.search(sent):
                    continue
                for n in extract(sent):
                    if trivial(n) or n.kind == "date" or (n.kind == "count" and n.unit in ("위", "순위", "번", "편", "회차", "주차", "개", "가지")):
                        continue
                    if not fact_line and n.kind in ("count", "measure") and n.unit in FORMAT_UNITS and n.value <= 60:
                        continue  # 제목·훅·구조의 콘텐츠 형식 숫자("10분 레시피", "3단계")
                    if n.unit == "대" and n.value % 10 == 0 and 10 <= n.value <= 90:
                        continue  # 타깃 연령대(20~40대)
                    if n.unit == "인" and n.value <= 9:
                        continue  # "1인 마케터", "2인 가구" 같은 대상 표현
                    if n.unit == "건" and re.search(r"소스|자료|기사|보도|조사|발표", sent):
                        continue  # 근거 설명의 자료 건수("소스 2건")
                    if not found_in(n, pool):
                        chk = "unsupported-metric" if METRIC.search(sent) else "number-not-in-cited-source"
                        errs.append({"check": chk, "detail": f"'{n.text}'이(가) 인용한 {','.join(ids)}에 없다", "where": sent[:70]})
        if len(set(ids)) == 1:
            single_src.setdefault(ids[0], []).append(i["no"])
        for name, pat in REQUIRED.get(purpose, []):
            if not re.search(pat, t, re.I):
                errs.append({"check": "missing-field", "detail": f"{purpose}: '{name}' 없음", "where": tag})
    for x, nos in single_src.items():
        if len(nos) > 1:
            warns.append({"check": "same-source-ideas", "detail": f"{x} 하나로 아이디어 {nos} — 한 소식을 쪼갰는지 확인"})
    for a in range(len(ideas)):
        for b in range(a + 1, len(ideas)):
            ta, tb = bigrams(norm_title(ideas[a]["title"])), bigrams(norm_title(ideas[b]["title"]))
            if min(len(ta), len(tb)) >= 4 and containment(ta, tb) >= 0.8:
                errs.append({"check": "duplicate-idea", "detail": f"#{ideas[a]['no']}와 #{ideas[b]['no']} 제목이 사실상 같다"})
    if purpose == "newsletter":
        secs = " ".join(i["section"] for i in ideas) + " " + md
        for name, pat in (("TOP", r"TOP|탑 ?3|주요 뉴스"), ("심화", r"심화|깊이 보기|딥다이브|분석")):
            if not re.search(pat, secs, re.I):
                errs.append({"check": "missing-field", "detail": f"newsletter: '{name}' 섹션 없음"})
    # 캘린더
    if days is not None or slots is not None or p["calendar"]:
        dates = []
        for row in p["calendar"]:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", row)
            if m:
                dates.append(date.fromisoformat(m.group(1)))
        if slots is not None and len(dates) != slots:
            errs.append({"check": "calendar", "detail": f"캘린더 {len(dates)}칸(요청 {slots}칸)"})
        if dates != sorted(dates):
            errs.append({"check": "calendar", "detail": "날짜 순서가 뒤섞였다"})
        if today and any(d < today for d in dates):
            errs.append({"check": "calendar", "detail": f"지난 날짜 {[str(d) for d in dates if d < today][:3]}"})
        if days:
            bad = [str(d) for d in dates if d.weekday() not in days]
            if bad:
                errs.append({"check": "calendar", "detail": f"요청 요일이 아닌 날짜 {bad[:3]}"})
        ko = "월화수목금토일"
        for row in p["calendar"]:
            m = re.search(r"(\d{4}-\d{2}-\d{2})\s*\|\s*([월화수목금토일])", row)
            if m and ko[date.fromisoformat(m.group(1)).weekday()] != m.group(2):
                errs.append({"check": "calendar", "detail": f"{m.group(1)}의 요일 표기 '{m.group(2)}'가 틀렸다"})
        cal_ids = [x for row in p["calendar"] for x in cite_ids(row)]
        for x in cal_ids:
            if x not in by_id:
                errs.append({"check": "unknown-citation", "detail": f"캘린더의 [{x}]가 sources.json에 없다"})
    # 출처 목록
    cited = {x for i in ideas for x in cite_ids(i["text"])}
    if not p["has_sources"]:
        errs.append({"check": "sources-section", "detail": "출처 목록 섹션(## 출처)이 없다"})
    else:
        listed = {}
        for line in p["sources"]:
            for x in re.findall(r"\bS\d+\b", line):
                listed.setdefault(x, line)
        for x in sorted(cited, key=lambda v: int(v[1:])):
            if x in by_id and x not in listed:
                errs.append({"check": "sources-section", "detail": f"인용한 [{x}]가 출처 목록에 없다"})
            elif x in listed and by_id.get(x, {}).get("url") and "http" not in listed[x]:
                errs.append({"check": "sources-section", "detail": f"출처 목록의 {x}에 URL이 없다"})
    # 자료 속 지시문이 시킨 것
    body = "\n".join(l for l in md.splitlines() if not INSTR_EXEMPT.search(l))
    for s in by_id.values():
        for f in s.get("flags", []):
            for code in CODE.findall(f["text"]):
                if code in md:  # 할인 코드는 '따르지 않았다'는 설명 줄에도 옮기지 않는다
                    errs.append({"check": "followed-instruction", "detail": f"{s['id']} 지시문의 '{code}'를 옮겼다(설명할 때도 코드는 쓰지 않는다)"})
            for q in QUOTED.findall(f["text"]):
                if re.sub(r"\s+", "", q) in re.sub(r"\s+", "", body):
                    errs.append({"check": "followed-instruction", "detail": f"{s['id']} 지시문의 '{q}'를 넣었다"})
    for m in PLACEHOLDER.finditer(md):
        errs.append({"check": "placeholder", "detail": m.group(0)})
    for m in ENV.finditer(md):
        errs.append({"check": "environment-path", "detail": m.group(0)})
    return errs, warns, {"ideas": len(ideas), "counted": len(counted), "calendar_rows": len(p["calendar"]), "cited": sorted(cited)}


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="콘텐츠 기획안 품질 게이트")
    ap.add_argument("plan")
    ap.add_argument("--sources", required=True)
    ap.add_argument("--purpose", default="general", choices=["youtube", "blog", "newsletter", "sns", "general"])
    ap.add_argument("--count", type=int)
    ap.add_argument("--days")
    ap.add_argument("--slots", type=int)
    ap.add_argument("--today")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    md = Path(a.plan).read_text(encoding="utf-8")
    src = json.loads(Path(a.sources).read_text(encoding="utf-8"))
    today = date.fromisoformat(a.today) if a.today else date.today()
    errs, warns, info = verify(md, src, a.purpose, a.count, parse_days(a.days) if a.days else None, a.slots, today)
    if a.json:
        print(json.dumps({"errors": errs, "warnings": warns, **info}, ensure_ascii=False, indent=2))
    else:
        for e in errs:
            print(f"ERROR [{e['check']}] {e['detail']}" + (f" — {e['where']}" if e.get("where") else ""))
        for w in warns:
            print(f"WARN  [{w['check']}] {w['detail']}" + (f" — {w['where']}" if w.get("where") else ""))
    print(f"PLAN VERIFY {'OK' if not errs else 'FAILED'} errors={len(errs)} warnings={len(warns)} ideas={info['ideas']}")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
