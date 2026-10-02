#!/usr/bin/env python3
"""highlights.json 검사 — 쇼츠를 인코딩하기 전에 통과시킨다(인코딩은 오래 걸리니 틀린 구간을 미리 잡는다).

오류
- schema: 목록이 아니거나 필수 필드(index·start·end·title·hook·subtitles) 누락. subtitles는 자막 생략이면 빈 배열([])로 명시
- range: start<0, end가 원본 길이 초과, start>=end
- length: 구간이 --min~--max초(기본 15~60) 밖
- overlap: 하이라이트끼리 구간이 겹치거나 index가 중복
- title / hook: 제목 28자, 후크 20자 초과
- subtitle-time: 자막 시간이 음수·역전·구간 길이 초과, 앞 자막과 겹침
경고
- 자막 한 줄이 7초 초과·0.8초 미만·40자 초과, 구간 시작·끝이 대본 문장 경계와 1초 넘게 어긋남(--transcript)

사용법: python validate_highlights.py <highlights.json> --source <W>/source.json [--transcript <W>/transcript.json] [--min 15 --max 60] [--json]
마지막 줄: HIGHLIGHTS OK n=N 또는 HIGHLIGHTS INVALID errors=N
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED = ("index", "start", "end", "title", "hook", "subtitles")


def validate(hl, duration: float | None, chunks: list | None = None, lo: float = 15, hi: float = 60) -> tuple[list, list]:
    errs, warns = [], []

    def e(check, where, detail):
        errs.append({"check": check, "where": where, "detail": detail})

    def w(check, where, detail):
        warns.append({"check": check, "where": where, "detail": detail})

    if not isinstance(hl, list) or not hl:
        e("schema", "-", "하이라이트 목록(JSON 배열)이 비었거나 배열이 아니다")
        return errs, warns
    seen, spans = set(), []
    for pos, h in enumerate(hl, 1):
        tag = f"#{h.get('index', pos) if isinstance(h, dict) else pos}"
        if not isinstance(h, dict):
            e("schema", tag, "항목이 객체가 아니다")
            continue
        miss = [k for k in REQUIRED if k not in h]
        if miss:
            e("schema", tag, f"필드 없음: {miss}" + (" (자막을 생략하려면 subtitles: [])" if "subtitles" in miss else ""))
        try:
            s, t = float(h.get("start")), float(h.get("end"))
        except (TypeError, ValueError):
            e("schema", tag, "start·end가 숫자가 아니다")
            continue
        if h.get("index") in seen:
            e("overlap", tag, f"index {h.get('index')} 중복")
        seen.add(h.get("index"))
        if s < 0 or t <= s:
            e("range", tag, f"구간 {s}~{t}")
            continue
        if duration and t > duration + 0.05:
            e("range", tag, f"끝 {t:.1f}s가 원본 길이 {duration:.1f}s를 넘는다")
        d = t - s
        if d < lo or d > hi:
            e("length", tag, f"{d:.1f}초(허용 {lo:g}~{hi:g}초)")
        for a, b, other in spans:
            if s < b and a < t:
                e("overlap", tag, f"{other}와 {max(a, s):.1f}~{min(b, t):.1f}s가 겹친다")
        spans.append((s, t, tag))
        title, hook = str(h.get("title", "")).strip(), str(h.get("hook", "")).strip()
        if len(title) > 28:
            e("title", tag, f"제목 {len(title)}자(28자 이내): {title}")
        if not hook:
            w("hook", tag, "후크가 비어 있다(제목이 대신 표시된다)")
        elif len(hook) > 20:
            e("hook", tag, f"후크 {len(hook)}자(20자 이내): {hook}")
        subs = h.get("subtitles")
        if isinstance(subs, list):
            prev_end = 0.0
            for i, sub in enumerate(subs, 1):
                try:
                    a, b, text = float(sub["start"]), float(sub["end"]), str(sub["text"])
                except (KeyError, TypeError, ValueError):
                    e("subtitle-time", tag, f"자막 {i}: start·end·text 형식 오류")
                    continue
                if a < 0 or b <= a:
                    e("subtitle-time", tag, f"자막 {i}: {a}~{b}")
                elif b > d + 0.3:
                    e("subtitle-time", tag, f"자막 {i} 끝 {b:.1f}s가 구간 길이 {d:.1f}s를 넘는다(시간은 구간 시작 기준 상대 초)")
                if a < prev_end - 0.05:
                    e("subtitle-time", tag, f"자막 {i}가 앞 자막과 겹친다({a:.1f} < {prev_end:.1f})")
                prev_end = max(prev_end, b)
                if b - a > 7:
                    w("subtitle-length", tag, f"자막 {i}가 {b - a:.1f}초 — 나눠 쓴다")
                elif 0 < b - a < 0.8:
                    w("subtitle-length", tag, f"자막 {i}가 {b - a:.1f}초 — 읽기 어렵다")
                if len(text) > 40:
                    w("subtitle-length", tag, f"자막 {i}가 {len(text)}자 — 두 줄 이내로")
        elif subs is not None:
            e("schema", tag, "subtitles는 배열이어야 한다")
        if chunks:
            starts = [c["timestamp"][0] for c in chunks]
            ends = [c["timestamp"][1] for c in chunks]
            if min(abs(s - x) for x in starts) > 1.0:
                w("boundary", tag, f"시작 {s:.1f}s가 대본 문장 시작과 1초 넘게 어긋난다 — 말 중간에서 시작하는지 확인")
            if min(abs(t - x) for x in ends) > 1.0:
                w("boundary", tag, f"끝 {t:.1f}s가 대본 문장 끝과 1초 넘게 어긋난다 — 말 중간에서 끊기는지 확인")
    return errs, warns


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="highlights.json 검사")
    ap.add_argument("highlights")
    ap.add_argument("--source")
    ap.add_argument("--duration", type=float)
    ap.add_argument("--transcript")
    ap.add_argument("--min", type=float, default=15)
    ap.add_argument("--max", type=float, default=60)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        hl = json.loads(Path(a.highlights).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as ex:
        print(f"ERROR [schema] JSON을 읽지 못했다: {ex}")
        print("HIGHLIGHTS INVALID errors=1")
        return 1
    duration = a.duration
    if a.source and not duration:
        duration = float(json.loads(Path(a.source).read_text(encoding="utf-8")).get("duration") or 0) or None
    chunks = json.loads(Path(a.transcript).read_text(encoding="utf-8")).get("chunks") if a.transcript else None
    errs, warns = validate(hl, duration, chunks, a.min, a.max)
    if a.json:
        print(json.dumps({"errors": errs, "warnings": warns}, ensure_ascii=False, indent=2))
    else:
        for x in errs:
            print(f"ERROR [{x['check']}] {x['where']} {x['detail']}")
        for x in warns:
            print(f"WARN  [{x['check']}] {x['where']} {x['detail']}")
    n = len(hl) if isinstance(hl, list) else 0
    print(f"HIGHLIGHTS OK n={n} warnings={len(warns)}" if not errs else f"HIGHLIGHTS INVALID errors={len(errs)} warnings={len(warns)}")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
