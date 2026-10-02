#!/usr/bin/env python3
"""소스 목록(sources.json)에서 통계를 낸다. 해석(논조·신호·전망)은 Claude가 하고, 이 스크립트는 셀 수 있는 것만 센다.

- 단어별 언급 소스 수(한국어 조사·어미를 떼고 센다. "알룰로스를"·"알룰로스처럼" → 알룰로스)
- 두 단어 구(인접 단어 쌍)의 언급 소스 수
- 월별·주별 소스 수, 상위 단어의 월별 추이, 기간 앞·뒤 절반 비교로 늘어난 단어
- 숫자 근거표: 소스마다 숫자가 든 문장(보고서에 숫자를 쓸 때 여기서 고르고 [S번호]를 단다)

논조(긍정·부정) 비율은 세지 않는다. 단어 사전으로 센 비율은 틀리기 쉽고 근거를 댈 수 없다. 논조는 Claude가 기사를 읽고 서술한다.

사용법: python trend_stats.py sources.json --out stats.json [--top 20] [--include-undated] [--json]
마지막 줄: STATS DONE sources=N terms=N facts=N
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "_vendor"))  # 공유 엔진(numparse·prepare_sources)
from numparse import extract, is_year  # noqa: E402
from prepare_sources import sentences  # noqa: E402

JOSA = sorted(["에서는", "에서도", "으로는", "으로도", "이라는", "라는", "에게서", "에서", "으로", "에게", "부터", "까지", "처럼", "보다",
               "이다", "와의", "과의", "이나", "에는", "에도", "만큼", "마다", "께서", "들이", "들은", "들을", "들의",
               "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "만", "로", "들"], key=len, reverse=True)
STOP = set("""있다 있는 있어 없다 했다 한다 하는 하고 해서 했고 됐다 된다 되는 되고 이번 지난 올해 지난해 내년 대한 위해 통해 관련 등 및 수 더
그 이 저 것 것으로 것이 것은 때문 때문에 경우 정도 가장 함께 이후 이전 최근 현재 당시 대해 따라 따르면 밝혔다 말했다 전했다 했다고 설명했다
기자 뉴스 기사 사진 제공 무단 배포 금지 대비 대부분 일부 각각 모두 또한 한편 다만 하지만 그러나 the and for with that this from are was were
have has been will its into about than more also not but
크게 많이 높게 낮게 빠르게 다시 이미 아직 계속 거의 매우 특히 가장 더욱 점점 새로 같은 다른 이런 그런 어떤""".split())


# 조사처럼 끝나지만 명사의 일부인 끝말(바른제로의 '로', 정도의 '도', 결과의 '과' …)
PROTECT = ("제로", "프로", "유로", "크로", "레트로", "히어로", "경로", "통로", "진로", "도로",
           "정도", "제도", "속도", "온도", "농도", "태도", "강도", "밀도", "빈도", "한도", "용도", "지도", "각도", "고도", "시도",
           "의도", "척도", "진도", "연도", "년도", "매도", "아이", "차이", "높이", "길이", "넓이", "나이", "사이", "평가", "증가",
           "추가", "국가", "단가", "원가", "주가", "물가", "고가", "저가", "특가", "정가", "회의", "정의", "논의", "합의", "동의",
           "문의", "주의", "강의", "불만", "비만", "결과", "효과", "성과", "통과", "초과", "부과")


def strip_josa(w: str) -> str:
    """조사를 뗀다. 떼면 명사 끝말이 깨지면 두고, 남는 말이 한 글자면 ''(원으로·것이 같은 군더더기)."""
    for j in JOSA:
        if w.endswith(j):
            stem = w[: -len(j)]
            if w.endswith(PROTECT) and not stem.endswith(PROTECT):
                return w
            return stem if len(stem) >= 2 else ""
    return w


def tokens(text: str) -> list[str]:
    out = []
    for raw in re.findall(r"[가-힣A-Za-z][가-힣A-Za-z0-9]*", text):
        w = strip_josa(raw) if re.search(r"[가-힣]", raw) else raw.lower()
        if len(w) < 2 or w in STOP or w.lower() in STOP:
            continue
        if re.search(r"[가-힣]", w) and len(w) >= 3 and re.search(r"(다|다고|다며|다는|다면)$", w):  # 늘었다·밝혔다고 같은 서술어
            continue
        out.append(w)
    return out


def week_of(d: str) -> str:
    y, m, dd = (int(x) for x in d.split("-"))
    iso = date(y, m, dd).isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def compute(src: dict, top: int = 20, include_undated: bool = False) -> dict:
    use = [s for s in src["sources"] if s["status"] == "kept" or (include_undated and s["status"] == "undated")]
    df: Counter = Counter()
    bdf: Counter = Counter()
    where: dict[str, list[str]] = defaultdict(list)
    per_month_terms: dict[str, Counter] = defaultdict(Counter)
    for s in use:
        toks = tokens(f"{s['title']}\n{s['text']}")
        uniq = set(toks)
        for w in uniq:
            df[w] += 1
            where[w].append(s["id"])
            if s["date"]:
                per_month_terms[s["date"][:7]][w] += 1
        for a, b in set(zip(toks, toks[1:])):
            if a != b:
                bdf[f"{a} {b}"] += 1
    months = Counter(s["date"][:7] for s in use if s["date"])
    weeks = Counter(week_of(s["date"]) for s in use if s["date"])
    top_terms = [{"term": w, "sources": n, "ids": where[w]} for w, n in df.most_common() if n >= 2][:top]
    # 기간 앞·뒤 절반 비교(소스 날짜 중앙값 기준)
    dated = sorted(s["date"] for s in use if s["date"])
    rising = []
    if len(dated) >= 4:
        mid = dated[len(dated) // 2]
        early = [s for s in use if s["date"] and s["date"] < mid]
        late = [s for s in use if s["date"] and s["date"] >= mid]
        ce, cl = Counter(), Counter()
        for grp, c in ((early, ce), (late, cl)):
            for s in grp:
                c.update(set(tokens(f"{s['title']}\n{s['text']}")))
        for w in set(cl) | set(ce):
            se, sl = ce[w] / max(len(early), 1), cl[w] / max(len(late), 1)
            if cl[w] >= 2 and sl - se >= 0.25:
                rising.append({"term": w, "early_share": round(se, 2), "late_share": round(sl, 2), "late_sources": cl[w]})
        rising.sort(key=lambda r: (r["late_share"] - r["early_share"], r["late_sources"]), reverse=True)
        rising = rising[:top]
    facts = []
    for s in use:
        for sent in sentences(s["text"]):
            nums = [n for n in extract(sent) if not is_year(n)]
            if nums:
                facts.append({"source": s["id"], "date": s["date"], "tier": s["tier"], "numbers": [n.text for n in nums], "sentence": sent})
    trend = {t["term"]: {m: per_month_terms[m][t["term"]] for m in sorted(per_month_terms)} for t in top_terms[:10]}
    return {"sources_used": [s["id"] for s in use], "by_month": dict(sorted(months.items())), "by_week": dict(sorted(weeks.items())),
            "top_terms": top_terms, "top_phrases": [{"phrase": p, "sources": n} for p, n in bdf.most_common() if n >= 2][:top],
            "term_by_month": trend, "rising": rising, "facts": facts,
            "doc_freq": {w: n for w, n in df.items()}}


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="소스 목록 통계")
    ap.add_argument("sources")
    ap.add_argument("--out", required=True)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--include-undated", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    src = json.loads(Path(a.sources).read_text(encoding="utf-8"))
    st = compute(src, a.top, a.include_undated)
    Path(a.out).write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    if a.json:
        print(json.dumps({k: v for k, v in st.items() if k != "doc_freq"}, ensure_ascii=False, indent=2))
    else:
        print(f"사용한 소스 {len(st['sources_used'])}건, 월별 {st['by_month']}")
        print("상위 단어(언급 소스 수): " + ", ".join(f"{t['term']} {t['sources']}" for t in st["top_terms"][:15]))
        if st["top_phrases"]:
            print("상위 구: " + ", ".join(f"{p['phrase']} {p['sources']}" for p in st["top_phrases"][:8]))
        if st["rising"]:
            print("늘어난 단어(앞 절반 → 뒤 절반 소스 비율): " + ", ".join(
                f"{r['term']} {r['early_share']:.0%}→{r['late_share']:.0%}" for r in st["rising"][:8]))
        print(f"숫자 근거표 {len(st['facts'])}문장 (stats.json의 facts)")
    print(f"STATS DONE sources={len(st['sources_used'])} terms={len(st['top_terms'])} facts={len(st['facts'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
