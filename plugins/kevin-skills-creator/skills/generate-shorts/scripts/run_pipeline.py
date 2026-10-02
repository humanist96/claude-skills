#!/usr/bin/env python3
"""한 번에 실행(시험용): 원본 준비 → 후보 선별 → (큐레이션 없이) 하이라이트 → 쇼츠 생성 → 검사.

규칙 점수만으로 구간을 고르고 제목·자막이 대본 그대로라 품질이 낮다. 실제 결과물은 SKILL.md의 큐레이션 워크플로로 만든다.
--candidates-only로 후보까지만 만들고 Claude가 highlights.json을 쓰는 방식이 기본이다.

사용법
  python run_pipeline.py --video 강의.mp4 --subs 강의.srt --output <W> --candidates-only
  python run_pipeline.py --video 강의.mp4 --stt --output <W> --count 3
  python run_pipeline.py --url "https://youtu.be/..." --i-have-rights --output <W> --candidates-only
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable  # Windows에서 'python3'는 스토어 안내 프로그램일 수 있어 지금 실행 중인 파이썬을 쓴다


def run(name: str, args: list[str], timeout: int = 1800) -> bool:
    print(f"\n=== {name} ===")
    t0 = time.time()
    try:
        r = subprocess.run([PY, *args], timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"[{name}] 타임아웃")
        return False
    print(f"[{name}] {'완료' if r.returncode == 0 else f'실패(exit {r.returncode})'} ({time.time() - t0:.0f}초)")
    return r.returncode == 0


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="쇼츠 파이프라인(시험용 한 번에 실행)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--video")
    src.add_argument("--url")
    ap.add_argument("--subs")
    ap.add_argument("--stt", action="store_true")
    ap.add_argument("--i-have-rights", action="store_true")
    ap.add_argument("--lang", default="ko")
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--layout", default="fit_blur")
    ap.add_argument("--output", default="output")
    ap.add_argument("--candidates-only", action="store_true", help="후보까지만 만들고 멈춘다(큐레이션 모드, 권장)")
    a = ap.parse_args(argv)
    out = Path(a.output)
    prep = [str(HERE / "prepare_source.py"), "--output", str(out), "--lang", a.lang]
    if a.video:
        prep += ["--video", a.video] + (["--subs", a.subs] if a.subs else []) + (["--stt"] if a.stt else [])
    else:
        prep += ["--url", a.url] + (["--i-have-rights"] if a.i_have_rights else [])
    if not run("1. 원본·대본 준비", prep):
        return 1
    if a.candidates_only:
        ok = run("2. 후보 선별", [str(HERE / "select_highlights.py"), "--transcript", str(out / "transcript.json"),
                                 "--output", str(out / "candidates.json"), "--mode", "candidates", "--lang", a.lang])
        if ok:
            print(f"\n다음: {out / 'candidates.json'}와 {out / 'transcript_timestamped.txt'}를 읽고 {out / 'highlights.json'}을 쓴다(SKILL.md 3단계)")
        return 0 if ok else 1
    if not run("2. 하이라이트(규칙 점수만)", [str(HERE / "select_highlights.py"), "--transcript", str(out / "transcript.json"),
                                          "--output", str(out / "highlights.json"), "--count", str(a.count), "--lang", a.lang]):
        return 1
    gen = [str(HERE / "generate_shorts.py"), "--highlights", str(out / "highlights.json"), "--output", str(out / "shorts"),
           "--srt", str(out / "transcript.srt"), "--layout", a.layout]
    gen += ["--video", a.video] if a.video else ["--url", a.url]
    if not run("3. 쇼츠 생성", gen):
        return 1
    return 0 if run("4. 검사", [str(HERE / "verify_short.py"), str(out / "shorts"), "--highlights", str(out / "highlights.json")]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
