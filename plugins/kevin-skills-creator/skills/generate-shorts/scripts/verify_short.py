#!/usr/bin/env python3
"""완성된 쇼츠 검사 — 프레임 눈 검수(3.5단계) 전에 기계로 볼 수 있는 것을 먼저 본다.

오류
- missing: highlights.json의 쇼츠 파일이 없거나 0바이트
- resolution: 해상도가 1080x1920이 아니다(--width/--height)
- duration: 길이가 하이라이트 구간과 1초 넘게 다르거나 15~60초(+인트로·아웃로) 밖
- audio: 오디오 트랙이 없다(업로드하면 무음)
- black: 앞·중간·끝 프레임이 모두 검다(인코딩·자막 합성 실패)
- overlay: metadata.json에 overlay=false(자막·후크 합성에 실패해 오버레이 없이 만들어졌다)
경고
- 프레임 하나만 검다, metadata.json에 항목이 없다

사용법: python verify_short.py <shorts 폴더> --highlights <W>/highlights.json [--json]
마지막 줄: SHORTS VERIFY OK n=N 또는 SHORTS VERIFY FAILED errors=N
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "_vendor"))
from media import frame_luma, probe  # noqa: E402

BLACK = 12.0  # 평균 밝기(0~255) 이하면 검은 프레임


def verify(shorts_dir: str, highlights: list, width: int = 1080, height: int = 1920, extra: float = 0.0) -> tuple[list, list, list]:
    errs, warns, rows = [], [], []
    meta_path = Path(shorts_dir) / "metadata.json"
    meta = {}
    if meta_path.is_file():
        try:
            meta = {s.get("index"): s for s in json.loads(meta_path.read_text(encoding="utf-8")).get("shorts", [])}
        except (json.JSONDecodeError, OSError):
            warns.append({"check": "metadata", "where": "-", "detail": "metadata.json을 읽지 못했다"})
    for pos, h in enumerate(highlights, 1):
        idx = int(h.get("index", pos))
        f = Path(shorts_dir) / f"short_{idx:02d}.mp4"
        tag = f.name
        if not f.is_file() or f.stat().st_size == 0:
            errs.append({"check": "missing", "where": tag, "detail": "파일이 없거나 비었다"})
            continue
        info = probe(str(f))
        want = float(h["end"]) - float(h["start"])
        row = {"file": tag, "duration": round(info["duration"], 1), "size": f"{info['width']}x{info['height']}", "audio": info["has_audio"]}
        if (info["width"], info["height"]) != (width, height):
            errs.append({"check": "resolution", "where": tag, "detail": f"{info['width']}x{info['height']}(기대 {width}x{height})"})
        if abs(info["duration"] - want) > 1.0 + extra:
            errs.append({"check": "duration", "where": tag, "detail": f"{info['duration']:.1f}초(구간 {want:.1f}초)"})
        if not (15 - 1 <= info["duration"] <= 60 + 1 + extra):
            errs.append({"check": "duration", "where": tag, "detail": f"{info['duration']:.1f}초 — 쇼츠는 15~60초"})
        if not info["has_audio"]:
            errs.append({"check": "audio", "where": tag, "detail": "오디오 트랙이 없다"})
        d = info["duration"] or want
        lumas = [frame_luma(str(f), t) for t in (0.5, d / 2, max(d - 1.0, 0.6))]
        dark = [l is not None and l <= BLACK for l in lumas]
        row["luma"] = [None if l is None else round(l, 1) for l in lumas]
        if all(dark):
            errs.append({"check": "black", "where": tag, "detail": f"앞·중간·끝 프레임이 모두 검다 {row['luma']}"})
        elif any(dark):
            warns.append({"check": "black", "where": tag, "detail": f"검은 프레임이 있다 {row['luma']}"})
        if meta.get(idx, {}).get("overlay") is False:
            errs.append({"check": "overlay", "where": tag, "detail": f"자막·후크 합성에 실패해 오버레이 없이 만들어졌다 — generate_shorts.py --only {idx} --force"})
        if meta and idx not in meta:
            warns.append({"check": "metadata", "where": tag, "detail": "metadata.json에 항목이 없다"})
        rows.append(row)
    return errs, warns, rows


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="완성 쇼츠 검사")
    ap.add_argument("shorts")
    ap.add_argument("--highlights", required=True)
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--extra", type=float, default=0.0, help="인트로·아웃로 카드를 켰다면 그 길이(초)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    hl = json.loads(Path(a.highlights).read_text(encoding="utf-8"))
    errs, warns, rows = verify(a.shorts, hl, a.width, a.height, a.extra)
    if a.json:
        print(json.dumps({"errors": errs, "warnings": warns, "shorts": rows}, ensure_ascii=False, indent=2))
    else:
        for r in rows:
            print(f"{r['file']}: {r['size']}, {r['duration']}초, 오디오 {'있음' if r['audio'] else '없음'}, 밝기 {r['luma']}")
        for x in errs:
            print(f"ERROR [{x['check']}] {x['where']} {x['detail']}")
        for x in warns:
            print(f"WARN  [{x['check']}] {x['where']} {x['detail']}")
    print(f"SHORTS VERIFY OK n={len(rows)}" if not errs else f"SHORTS VERIFY FAILED errors={len(errs)}")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
