#!/usr/bin/env python3
"""V2: media.py — ffmpeg 찾기(환경변수·PATH·imageio-ffmpeg), ffprobe 없이 정보 읽기, 필터 경로 이스케이프, 프레임 밝기."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shorts_fixtures import SCRIPTS  # noqa: E402

import media  # noqa: E402  (_shorts_fixtures가 _vendor를 경로에 넣었다)

results: list[tuple[str, bool, str]] = []
MEDIA = SCRIPTS / "_vendor" / "media.py"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ff = media.ffmpeg_path()
    results.append(("ffmpeg를 찾음", bool(ff), str(ff)))
    if not ff:
        print("FFMPEG MISSING — 설치 후 다시 실행(pip install imageio-ffmpeg)")
        print("MEDIA FAILED")
        return 1
    # 환경변수 우선, 없는 경로면 다음 순서로
    code = "import sys; sys.path.insert(0, r'%s'); import media; print(media.ffmpeg_path())" % (SCRIPTS / "_vendor")
    env = {**os.environ, "FFMPEG_BINARY": ff}
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    results.append(("FFMPEG_BINARY 환경변수 우선", r.stdout.strip() == ff, r.stdout.strip()))
    env = {**os.environ, "FFMPEG_BINARY": str(Path(tempfile.gettempdir()) / "no_such_ffmpeg.exe")}
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    results.append(("없는 환경변수 경로는 건너뜀", r.stdout.strip() not in ("", "None") and "no_such" not in r.stdout, r.stdout.strip()))
    cases = {r"C:\Users\a b\sub.ass": r"C\:/Users/a b/sub.ass", "/tmp/it's.ass": "/tmp/it'\\''s.ass"}
    for raw, want in cases.items():
        results.append((f"필터 경로 이스케이프 {raw}", media.filter_path(raw) == want, media.filter_path(raw)))
    with tempfile.TemporaryDirectory() as td:
        T = Path(td)
        a, b, black = T / "av.mp4", T / "v.mp4", T / "black.mp4"
        subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10", "-f", "lavfi", "-i",
                        "sine=frequency=440", "-t", "2", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(a)], check=True)
        subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=10", "-t", "3",
                        "-c:v", "libx264", str(b)], check=True)
        subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=320x240:r=10", "-t", "2",
                        "-c:v", "libx264", str(black)], check=True)
        pa, pb = media.probe(str(a)), media.probe(str(b))
        results.append(("정보: 오디오 있는 2초 320x240", abs(pa["duration"] - 2) < 0.2 and (pa["width"], pa["height"]) == (320, 240)
                        and pa["has_audio"], json.dumps(pa)))
        results.append(("정보: 오디오 없는 3초 640x360", abs(pb["duration"] - 3) < 0.2 and (pb["width"], pb["height"]) == (640, 360)
                        and not pb["has_audio"], json.dumps(pb)))
        results.append(("없는 파일은 길이 0", media.probe(str(T / "none.mp4"))["duration"] == 0, ""))
        lb, lt = media.frame_luma(str(black), 1.0), media.frame_luma(str(a), 1.0)
        results.append(("프레임 밝기: 검은 화면 ≈0, 테스트 패턴은 밝음", lb is not None and lb < 5 and lt is not None and lt > 40, f"{lb} {lt}"))
        r = subprocess.run([sys.executable, str(MEDIA), "--probe", str(a)], capture_output=True, text=True, encoding="utf-8")
        results.append(("CLI --probe", '"has_audio": true' in r.stdout, r.stdout[-200:]))
    bad = [x for x in results if not x[1]]
    for name, ok, why in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f" — {why}"))
    if bad:
        print(f"MEDIA FAILED ({len(bad)}/{len(results)})")
        return 1
    print(f"MEDIA OK — {len(results)}개 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
