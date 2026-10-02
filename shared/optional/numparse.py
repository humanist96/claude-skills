#!/usr/bin/env python3
"""숫자 추출·값 비교(trend_stats.py, verify_report.py 공용).

"1조 2,000억 원" = "1조2000억원" = "1.2조 원"처럼 표기가 달라도 값이 같으면 같은 숫자로 본다.
종류(kind)가 다르면 같은 값이어도 다른 숫자다: percent(%·%p·퍼센트), money(원·달러·$), date(연·월·일·분기),
measure(g·mL·kg 등 측정 단위), count(그 밖의 단위·단위 없음).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

KO_BIG = {"조": 1e12, "억": 1e8, "만": 1e4, "천": 1e3}
EN_BIG = {"trillion": 1e12, "billion": 1e9, "million": 1e6, "thousand": 1e3, "tn": 1e12, "bn": 1e9, "b": 1e9, "m": 1e6, "k": 1e3}
MEASURE_UNITS = ("mL", "ml", "kg", "km", "mg", "g", "L", "GB", "TB", "MB", "nm", "kWh", "MW", "GW", "TB/s", "GB/s", "℃", "도")
DATE_UNITS = ("년", "월", "일", "분기", "반기", "주차")
MONEY_WORDS = ("원", "달러", "엔", "위안", "유로")
SPACED_UNITS = set("원달러엔위안유로캔명개건곳종배병권회톤장편대퍼")

NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
KO_COMPOSITE = re.compile(rf"(?:(?:{NUM})\s?(?:조|억|만|천)\s?)+(?:{NUM})?")
TOKEN = re.compile(
    rf"(?P<cur>[$€£¥₩])?\s?(?P<num>(?:(?:{NUM})\s?(?:조|억|만|천)\s?)+(?:{NUM})?|{NUM})"
    r"(?P<en>\s?(?:trillion|billion|million|thousand|tn|bn|[bBmMkK])(?![A-Za-z]))?"
    r"(?P<sfx>\s?(?:%p|%|퍼센트포인트|퍼센트|%포인트|percentage points?|percent|pct|[A-Za-z]{1,4}/s|[A-Za-z]{1,3}|℃|[가-힣]{1,3}))?")
QUARTER = re.compile(r"\b[1-4]Q\d{2}\b|\bQ[1-4]\b|\bFY\d{2,4}\b|\b[1-4]H\d{2}\b"
                     r"|\b(?:19|20)\d{2}\s?[.\-/]\s?(?:[1-4][QH]|0?[1-9]|1[0-2])(?:\s?[.\-/]\s?\d{1,2})?(?![\d%])", re.I)  # 2025.11, 2026-07-08, 2025.3Q는 날짜
CITATION = re.compile(r"\[(?:S\d+(?:\s*[,，·]\s*S\d+)*)\]")
ORDINAL_PREFIX = re.compile(r"(?:^|\s)(?:제|No\.?|#)$")


@dataclass
class Num:
    text: str
    value: float
    kind: str
    unit: str
    start: int
    end: int


def _plain(s: str) -> float:
    return float(s.replace(",", ""))


def ko_value(s: str) -> float:
    total, cur = 0.0, ""
    for part in re.finditer(rf"({NUM})\s?(조|억|만|천)?", s):
        n, u = _plain(part.group(1)), part.group(2)
        total += n * KO_BIG[u] if u else n
        cur = u or ""
    return total


def _kind(sfx: str, cur: str) -> tuple[str, str]:
    s = sfx.strip()
    if s.startswith(("%", "퍼센트", "percent", "pct")):
        return "percent", "%p" if s.startswith("%p") or "포인트" in s or "points" in s or s.endswith("point") else "%"
    if cur or s.startswith(MONEY_WORDS) or s in ("USD", "KRW", "EUR", "JPY"):
        return "money", cur or s
    if s.startswith(DATE_UNITS):
        return "date", s
    if s in MEASURE_UNITS or s.endswith("/s"):
        return "measure", s
    return "count", s


def extract(text: str) -> list[Num]:
    """텍스트의 숫자. 인용 표시([S3])·분기 표기(3Q26)·서수(제1)는 건너뛴다."""
    masked = CITATION.sub(lambda m: " " * len(m.group(0)), text)
    masked = QUARTER.sub(lambda m: " " * len(m.group(0)), masked)
    out: list[Num] = []
    for m in TOKEN.finditer(masked):
        raw_num = m.group("num").strip()
        if not raw_num or not re.search(r"\d", raw_num):
            continue
        # 숫자(통화 기호 포함) 바로 앞 글자. 정규식 앞의 선택 공백 때문에 m.start()가 공백을 가리킬 수 있다
        st = m.start("cur") if m.group("cur") else m.start("num")
        prev = masked[max(0, st - 1):st]
        if prev and (prev.isalpha() and prev.isascii() or prev in "._/-#"):  # GPT-4o, v2.1, 3.5-turbo의 일부
            if not (prev == "-" and st >= 2 and masked[st - 2].isspace()):
                continue
        sfx = (m.group("sfx") or "")
        en = (m.group("en") or "").strip()
        cur = m.group("cur") or ""
        if re.search(r"[조억만천]", raw_num):
            v = ko_value(raw_num)
            raw_num = raw_num.rstrip()
        else:
            v = _plain(raw_num)
        if en:
            v *= EN_BIG[en.lower()]
        # 한글 접미어는 단위 단어 한 개만(“34%늘어” 같은 붙여쓰기 대비). 조사·어미로 끝나면 단위 아님
        s = sfx.strip()
        if s and sfx[:1].isspace() and re.fullmatch(r"[가-힣]{1,3}", s) and s[:1] not in SPACED_UNITS:
            s, sfx = "", ""  # "13.6B 매출", "3 사람"처럼 띄어 쓴 일반 단어는 단위가 아니다
        if en and s and re.fullmatch(r"[가-힣]{1,3}", s):
            s, sfx = "", ""
        if s and sfx[:1].isspace() and re.fullmatch(r"[A-Za-z]{1,4}(/s)?", s) and s not in MEASURE_UNITS and s not in ("USD", "KRW", "EUR", "JPY"):
            s, sfx = "", ""  # "2026 AI", "20 of"처럼 띄어 쓴 영어 단어는 단위가 아니다
        if s and not s.startswith("퍼센트") and re.fullmatch(r"[가-힣]{1,3}", s):
            s = s[:2] if s[:2] in ("분기", "반기", "주차", "시간", "개월", "퍼센") else s[:1]
            if s in ("이", "가", "은", "는", "을", "를", "의", "에", "로", "와", "과", "도", "만", "보", "까", "부", "씩", "여", "쯤", "께"):
                s = ""
        kind, unit = _kind(s, cur)
        if kind == "count" and en and not s:
            unit = en
        if s:
            end = m.start("sfx") + sfx.index(s) + len(s)
        elif en:
            end = m.end("en")
        else:
            end = m.start("num") + len(m.group("num").rstrip())
        out.append(Num(text=text[m.start():end].strip(), value=v, kind=kind, unit=unit, start=m.start(), end=end))
    # 범위 "20~59세": 앞 숫자가 단위를 물려받는다
    for a, b in zip(out, out[1:]):
        gap = text[a.end:b.start]
        if a.kind == "count" and not a.unit and re.fullmatch(r"\s?[~\-–]\s?", gap):
            a.kind, a.unit = b.kind, b.unit
    return out


def is_year(n: Num) -> bool:
    return n.kind == "date" or (n.kind == "count" and not n.unit and n.value.is_integer() and 1900 <= n.value <= 2100)


def trivial(n: Num) -> bool:
    """출처 검사에서 빼는 숫자: 연도·날짜, 단위 없는 9 이하 정수."""
    if is_year(n):
        return True
    return n.kind == "count" and not n.unit and n.value.is_integer() and abs(n.value) <= 9


def same(a: Num, b: Num) -> bool:
    if a.kind != b.kind:
        # "1조 5,000억"(원 생략) = "1조 5,000억 원": 큰 단위가 붙은 금액은 '원'을 빼고 쓰는 일이 많다
        big = re.search(r"[조억만]", a.text + b.text)
        if not (big and {a.kind, b.kind} == {"money", "count"} and "" in (a.unit, b.unit)):
            return False
    if a.kind == "percent" and a.unit != b.unit and "%p" in (a.unit, b.unit):
        return False
    if a.value == b.value:
        return True
    big = max(abs(a.value), abs(b.value))
    return big > 0 and abs(a.value - b.value) / big < 1e-9


def found_in(n: Num, pool: list[Num]) -> bool:
    return any(same(n, p) for p in pool)
