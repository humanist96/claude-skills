"""수집한 기사에서 셀 수 있는 것만 센다: 단어별 언급 기사 수, 날짜별 기사 수, 매체별 기사 수.

논조(긍정·부정) 비율은 세지 않는다. 단어 사전으로 센 비율은 틀리기 쉬워 보고서 신뢰를 떨어뜨린다.
"""
from __future__ import annotations

import re
from collections import Counter

JOSA = sorted(["에서는", "으로는", "에서", "으로", "에게", "부터", "까지", "처럼", "보다", "은", "는", "이", "가", "을", "를", "의",
               "에", "와", "과", "도", "만", "로"], key=len, reverse=True)
STOP = set("""있다 있는 했다 한다 하는 이번 지난 올해 대한 위해 통해 관련 등 및 수 더 것 기자 뉴스 사진 광고 무단 배포 금지 구독
the and for with that this from to of in on at by is are was were be it its as or an you your we our they their more most
like can will just how what when new now get make all about into than also not but has have had nbsp amp quot""".split())


def tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[가-힣A-Za-z][가-힣A-Za-z0-9]*", text):
        if re.search(r"[가-힣]", w):
            for j in JOSA:
                if w.endswith(j):
                    w = w[: -len(j)] if len(w) - len(j) >= 2 else ""
                    break
        else:
            w = w.lower()
        if len(w) >= 2 and w not in STOP and not (len(w) >= 3 and w.endswith("다")):
            out.append(w)
    return out


def analyze(collected: dict, keywords: list[str], top: int = 15) -> dict:
    items = collected["items"]
    df: Counter = Counter()
    kw_low = {k.lower() for k in keywords} | {t for k in keywords for t in tokens(k)}
    for it in items:
        df.update({w for w in tokens(f"{it['title']} {it['text']}") if w.lower() not in kw_low})
    return {
        "count": len(items),
        "by_date": dict(sorted(Counter(it["published"] or "날짜 없음" for it in items).items())),
        "by_publisher": dict(Counter(it["publisher"] for it in items).most_common(10)),
        "top_terms": [{"term": w, "articles": n} for w, n in df.most_common(top) if n >= 2],
    }
