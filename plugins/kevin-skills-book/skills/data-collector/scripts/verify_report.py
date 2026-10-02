#!/usr/bin/env python3
"""리서치 보고서 품질 게이트 — 사용자에게 전달하기 전에 반드시 통과시킨다.

보고서는 주장마다 [S3]처럼 sources.json의 번호로 출처를 달고, 끝에 출처 목록(번호·제목·매체·날짜·URL)을 둔다.

오류(전달 금지)
- uncited-number: 숫자가 든 문단·항목·표 행에 출처 번호가 없다(출처 목록·조사 방법 섹션 제외)
- number-not-in-cited-source: 문장의 숫자가 인용한 소스 본문에 없다(표기 차이는 허용: 1.2조 원 = 1조 2,000억 원).
  계산한 값은 문장에 "(계산: …)"을 붙이면 출처 대조에서 빠진다
- unknown-citation: sources.json에 없는 번호
- out-of-window-as-current: 요청 기간 밖 소스를 날짜 표시 없이 인용(과거 맥락이면 그 연도·월을 문장에 쓴다)
- sources-section: 출처 목록이 없거나, 인용한 번호가 목록에 없거나, 목록 항목에 URL이 없다
- investment-advice: 매수·매도 권유, 목표 주가 제시, "사도 된다" 같은 투자 판단
- disclaimer-missing: 금융·부동산·종목 관련 보고서인데 "투자 조언이 아니다" 고지가 없다
- unsupported-sentiment-ratio: "긍정 67%"처럼 근거 없는 논조 비율
- followed-instruction: 자료 속 지시문(prepare_sources의 FLAG)이 시킨 주장을 보고서에 썼다
- placeholder: [링크]·TODO·○○·[출처 필요] 같은 미완성 표시
- environment-path: claude.ai 컨테이너 출력 폴더·파일 제공 도구 이름 같은 특정 환경 전용 표현
경고
- 중복 소스 인용(원본 번호로 바꾼다), 날짜 없는 소스 인용, 보도자료·블로그(D등급)만으로 뒷받침한 문장, 인용한 소스 3곳 미만

사용법
  python verify_report.py <report.md> [--sources sources.json] [--domain finance] [--json]
마지막 줄: REPORT VERIFY OK 또는 REPORT VERIFY FAILED
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "_vendor"))  # 공유 엔진(numparse·prepare_sources)
from numparse import extract, found_in, trivial  # noqa: E402

CITE = re.compile(r"\[(S\d+(?:\s*[,，·/]\s*S?\d+)*)\]")
SOURCES_HEAD = re.compile(r"^#{1,4}\s*.*(출처|참고 ?자료|참고문헌|소스 목록|Sources|References)", re.I)
EXEMPT_HEAD = re.compile(r"^#{1,4}\s*.*(분석 메타데이터|수집 개요|조사 방법|방법론|수집 방법|Methodology|About this report)", re.I)
CALC = re.compile(r"\(계산[:：][^)]*\)|\(계산\)")
ADVICE = re.compile(
    r"(매수|매도|비중 ?확대|비중 ?축소|분할 ?매수|저가 ?매수|손절)\s?(를|을)?\s?(추천|권유|권장|하세요|하라|할 ?때|적기|기회|타이밍|의견)"
    r"|목표 ?주가|(사도|팔아도) (된다|좋다|괜찮)|지금 (사|팔)(라|세요|야)|담아(라|두세요|둘 만)|투자(를|하기를)? (추천|권합니다|권한다)"
    r"|strong buy|buy rating|sell rating|price target|you should (buy|sell)", re.I)
NEGATION = re.compile(r"아니|아닙|않|금지|삼가|하지 마|드리지|not (investment|financial) advice|no recommendation", re.I)
DISCLAIMER = re.compile(r"투자 ?(조언|권유|추천|자문)[^.\n]{0,12}(아니|아닙|않)|(매수|매도)[·/ ]*(매수|매도)? ?(추천|권유|의견)[^.\n]{0,8}(아니|아닙|않|드리지)"
                        r"|not (investment|financial) advice", re.I)
SENTIMENT = re.compile(r"(긍정|부정|중립|낙관|비관)[^\n%]{0,8}\d+(?:\.\d+)?\s?%|(센티먼트|감성|논조)[^\n]{0,30}\d+(?:\.\d+)?\s?%")
PLACEHOLDER = re.compile(r"\[(?:링크|URL|url|출처 ?필요|여기[^\]]*|TBD|추가 예정)\]|\bTODO\b|\bTBD\b|XXX|○○|\{\{[^}]*\}\}")
ENV = re.compile("/mnt/" + "user-data|present" + "_files")  # 정적 검증기가 리터럴을 환경 종속으로 보므로 나눠 쓴다
INSTR_EXEMPT = re.compile(r"지시|무시|반영하지|따르지|삽입된 문구|주입")
QUOTED = re.compile(r"['‘\"“「]([^'’\"”」]{4,80})['’\"”」]")


def cite_ids(s: str) -> list[str]:
    out = []
    for m in CITE.finditer(s):
        for part in re.split(r"\s*[,，·/]\s*", m.group(1)):
            part = part.strip()
            out.append(part if part.startswith("S") else "S" + part)
    return out


def blocks(md: str) -> list[dict]:
    """문단·목록 항목·표 행 단위 블록과 그 블록이 속한 섹션 종류."""
    out, cur, section = [], [], "body"

    def flush():
        if cur:
            out.append({"text": "\n".join(cur), "section": section})
            cur.clear()
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("#"):
            flush()
            section = "sources" if SOURCES_HEAD.match(s) else "exempt" if EXEMPT_HEAD.match(s) else "body"
            out.append({"text": s, "section": "heading"})
            continue
        if not s:
            flush()
            continue
        if re.match(r"^([-*+]|\d+[.)])\s|^\|", s):
            flush()
            if re.fullmatch(r"\|[\s:|-]+\|?", s):
                continue
            out.append({"text": s, "section": section})
            continue
        if s.startswith(">"):  # 머리 안내(기준일·기간·자료 수)는 출처 번호 대상이 아니다
            flush()
            out.append({"text": s, "section": "exempt" if section == "body" else section})
            continue
        cur.append(s)
    flush()
    return out


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+(?=[^\[])|(?<=다\.)\s*", text)
    return [p for p in parts if p.strip()]


def verify(md: str, src: dict | None, domain: str = "") -> tuple[list, list, dict]:
    errs, warns = [], []
    by_id = {s["id"]: s for s in (src or {}).get("sources", [])}
    pools = {i: extract(f"{s['title']}\n{s['text']}") for i, s in by_id.items()}
    bl = blocks(md)
    summ = (src or {}).get("summary", {})
    meta_counts = {float(v) for v in [summ.get("total", -1), *summ.get("status", {}).values()]}  # "13건 중 9건 사용" 같은 수집 개요
    body_text = "\n".join(b["text"] for b in bl if b["section"] in ("body", "heading"))
    cited_all: set[str] = set()

    for b in bl:
        if b["section"] != "body":
            continue
        t = b["text"]
        ids = cite_ids(t)
        cited_all.update(ids)
        for i in ids:
            if src is not None and i not in by_id:
                errs.append({"check": "unknown-citation", "detail": f"[{i}]가 sources.json에 없다", "where": t[:60]})
        nums = [n for n in extract(CALC.sub(" ", t)) if not trivial(n) and not (n.unit == "건" and n.value in meta_counts)]
        if nums and not ids:
            errs.append({"check": "uncited-number", "detail": f"숫자 {', '.join(n.text for n in nums[:4])}에 출처 번호가 없다", "where": t[:80]})
            continue
        if src is None or not ids:
            continue
        for sent in split_sentences(t):
            sids = cite_ids(sent) or ids
            snums = [n for n in extract(CALC.sub(" ", sent)) if not trivial(n) and not (n.unit == "건" and n.value in meta_counts)]
            if CALC.search(sent):
                warns.append({"check": "calculated", "detail": "계산 값(출처 대조 제외) — 계산식을 확인한다", "where": sent[:60]})
            pool = [n for i in sids if i in pools for n in pools[i]]
            for n in snums:
                if not found_in(n, pool):
                    item = {"check": "number-not-in-cited-source", "detail": f"'{n.text}'이(가) 인용한 {','.join(sids)}에 없다", "where": sent[:80]}
                    (warns if CALC.search(sent) else errs).append(item)  # 계산식을 밝힌 값은 경고로 남긴다
            known = [by_id[i] for i in sids if i in by_id]
            for s in known:
                if s["status"] == "out_of_window":
                    y, ym = s["date"][:4], s["date"][:7]
                    if not (re.search(rf"{y}\s?년|{y}[.\-/]", sent) or ym in sent):
                        errs.append({"check": "out-of-window-as-current",
                                     "detail": f"{s['id']}({s['date']})는 요청 기간 밖이다 — 과거 맥락이면 연도·월을 밝힌다", "where": sent[:60]})
                elif s["status"] == "duplicate":
                    warns.append({"check": "duplicate-cited", "detail": f"{s['id']}는 {s.get('duplicate_of')}의 중복이다 — 원본 번호로", "where": sent[:60]})
                elif s["status"] == "undated":
                    warns.append({"check": "undated-cited", "detail": f"{s['id']}는 날짜가 없다", "where": sent[:60]})
            if known and snums and all(s["tier"] == "D" for s in known):
                warns.append({"check": "weak-source-only", "detail": f"보도자료·블로그({','.join(s['id'] for s in known)})만으로 뒷받침", "where": sent[:60]})

    # 출처 목록
    src_lines = [b["text"] for b in bl if b["section"] == "sources"]
    if not any(SOURCES_HEAD.match(b["text"]) for b in bl if b["section"] == "heading"):
        errs.append({"check": "sources-section", "detail": "출처 목록 섹션(## 출처)이 없다"})
    else:
        listed = {}
        for line in src_lines:
            for i in re.findall(r"\bS\d+\b", line):
                listed.setdefault(i, line)
        if src is not None:
            for i in sorted(cited_all, key=lambda x: int(x[1:])):
                if i in by_id and i not in listed:
                    errs.append({"check": "sources-section", "detail": f"인용한 [{i}]가 출처 목록에 없다"})
                elif i in listed and by_id.get(i, {}).get("url") and "http" not in listed[i]:
                    errs.append({"check": "sources-section", "detail": f"출처 목록의 {i}에 URL이 없다"})
        url_lines = [l for l in src_lines if "http" in l]
        if not url_lines and (src is None or any(by_id.get(i, {}).get("url") for i in cited_all)):
            errs.append({"check": "sources-section", "detail": "출처 목록에 URL이 하나도 없다"})

    # 투자 권유·면책·논조: 출처 목록의 항목 줄(번호·URL이 있는 줄)만 빼고 모두 본다
    def is_source_row(b: dict) -> bool:
        return b["section"] == "sources" and bool(re.search(r"\bS\d+\b|https?://", b["text"]))
    body_text = "\n".join(b["text"] for b in bl if not is_source_row(b))
    for b in bl:
        if is_source_row(b):
            continue
        for sent in split_sentences(b["text"]):
            m = ADVICE.search(sent)
            if m and not NEGATION.search(sent):
                errs.append({"check": "investment-advice", "detail": m.group(0), "where": sent[:80]})
    if (domain in ("finance", "realestate") or advice_topic(body_text)) and not DISCLAIMER.search(md):
        errs.append({"check": "disclaimer-missing", "detail": "금융·부동산·종목 내용인데 '투자 조언이 아니다' 고지가 없다"})

    for m in SENTIMENT.finditer(body_text):
        errs.append({"check": "unsupported-sentiment-ratio", "detail": m.group(0)})
    for m in PLACEHOLDER.finditer(md):
        errs.append({"check": "placeholder", "detail": m.group(0)})
    for m in ENV.finditer(md):
        errs.append({"check": "environment-path", "detail": m.group(0)})

    # 자료 속 지시문이 시킨 주장
    flat_report = [(b["text"], re.sub(r"\s+", "", b["text"])) for b in bl if b["section"] in ("body", "exempt", "heading")]
    for s in by_id.values():
        for f in s.get("flags", []):
            for q in QUOTED.findall(f["text"]):
                payload = re.sub(r"\s+", "", q)
                for raw, flat in flat_report:
                    for sent in split_sentences(raw):
                        if INSTR_EXEMPT.search(sent):
                            continue
                        if payload in re.sub(r"\s+", "", sent) or _all_terms(q, sent):
                            errs.append({"check": "followed-instruction",
                                         "detail": f"{s['id']}의 지시문이 시킨 주장 '{q}'을 썼다", "where": sent[:80]})

    if src is not None and 0 < len({i for i in cited_all if i in by_id}) < 3:
        warns.append({"check": "few-sources", "detail": f"인용한 소스가 {len(cited_all)}곳이다 — 자료 부족을 보고서에 밝힌다"})
    info = {"cited": sorted(cited_all, key=lambda x: int(x[1:]) if x[1:].isdigit() else 0), "blocks": len(bl)}
    return errs, warns, info


def advice_topic(text: str) -> bool:  # 종목·자산 투자 맥락이 실제로 있는가(업종 기사에 '투자'가 한 번 나온 정도는 제외)
    return len(re.findall(r"주가|주식|종목|매수|매도|시가총액|목표가|코스피|코스닥|ETF|투자 판단|투자 관점|청약|분양가|전셋값|매매가", text)) >= 2


def _all_terms(q: str, sent: str) -> bool:
    terms = [w for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", q)]
    terms = [re.sub(r"(이|가|은|는|을|를|의|라고|이라고)$", "", w) for w in terms]
    terms = [w for w in terms if len(w) >= 2]
    return len(terms) >= 3 and all(w in sent for w in terms)


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="리서치 보고서 품질 게이트")
    ap.add_argument("report")
    ap.add_argument("--sources")
    ap.add_argument("--domain", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    md = Path(a.report).read_text(encoding="utf-8")
    src = json.loads(Path(a.sources).read_text(encoding="utf-8")) if a.sources else None
    errs, warns, info = verify(md, src, a.domain)
    if src is None:
        warns.append({"check": "no-sources", "detail": "sources.json이 없어 숫자 출처 대조를 하지 않았다"})
    if a.json:
        print(json.dumps({"errors": errs, "warnings": warns, **info}, ensure_ascii=False, indent=2))
    else:
        for e in errs:
            print(f"ERROR [{e['check']}] {e['detail']}" + (f" — {e['where']}" if e.get("where") else ""))
        for w in warns:
            print(f"WARN  [{w['check']}] {w['detail']}" + (f" — {w['where']}" if w.get("where") else ""))
    print(f"REPORT VERIFY {'OK' if not errs else 'FAILED'} errors={len(errs)} warnings={len(warns)} cited={len(info['cited'])}")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
