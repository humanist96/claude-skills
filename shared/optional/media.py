#!/usr/bin/env python3
"""영상·음성 처리 공용: ffmpeg 찾기, 길이·해상도·오디오 확인, 필터 경로 이스케이프, 프레임 밝기.

ffmpeg를 찾는 순서
  1. 환경변수 FFMPEG_BINARY
  2. PATH의 ffmpeg
  3. imageio-ffmpeg 패키지에 들어 있는 ffmpeg(pip install imageio-ffmpeg — 관리자 권한 없이 설치 가능)
ffprobe가 없어도 동작한다(ffmpeg -i 출력에서 정보를 읽는다).

CLI: python media.py --check            # ffmpeg 위치와 버전
     python media.py --probe <파일>      # JSON: duration·width·height·fps·has_audio
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache


@lru_cache(maxsize=1)
def ffmpeg_path() -> str | None:
    env = os.environ.get("FFMPEG_BINARY")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg  # type: ignore
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return exe
    except Exception:  # noqa: BLE001 — 패키지가 없거나 바이너리를 못 받으면 None
        pass
    return None


@lru_cache(maxsize=1)
def ffprobe_path() -> str | None:
    found = shutil.which("ffprobe")
    if found:
        return found
    ff = ffmpeg_path()
    if ff:
        cand = os.path.join(os.path.dirname(ff), "ffprobe" + (".exe" if ff.lower().endswith(".exe") else ""))
        if os.path.isfile(cand):
            return cand
    return None


def require_ffmpeg() -> str:
    ff = ffmpeg_path()
    if not ff:
        raise SystemExit("ffmpeg를 찾지 못했다. 설치: Windows 'winget install Gyan.FFmpeg' 또는 'pip install imageio-ffmpeg', "
                         "macOS 'brew install ffmpeg', Linux 'sudo apt-get install -y ffmpeg'")
    return ff


def run(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    """ffmpeg를 찾은 경로로 실행한다(args[0]이 'ffmpeg'면 바꿔 넣는다)."""
    if args and args[0] == "ffmpeg":
        args = [require_ffmpeg(), *args[1:]]
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def _hms(s: str) -> float:
    h, m, sec = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def probe(path: str) -> dict:
    """{"duration", "width", "height", "fps", "has_audio", "has_video"}. 읽지 못하면 duration 0."""
    info = {"duration": 0.0, "width": 0, "height": 0, "fps": 0.0, "has_audio": False, "has_video": False}
    if not os.path.isfile(path):
        return info
    fp = ffprobe_path()
    if fp:
        r = subprocess.run([fp, "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", path],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        try:
            data = json.loads(r.stdout)
            info["duration"] = float(data.get("format", {}).get("duration", 0) or 0)
            for st in data.get("streams", []):
                if st.get("codec_type") == "video" and not info["has_video"]:
                    info.update(has_video=True, width=int(st.get("width", 0)), height=int(st.get("height", 0)))
                    num, _, den = (st.get("r_frame_rate") or "0/1").partition("/")
                    info["fps"] = round(float(num) / float(den), 2) if den and float(den) else 0.0
                elif st.get("codec_type") == "audio":
                    info["has_audio"] = True
            return info
        except (json.JSONDecodeError, ValueError):
            pass
    ff = ffmpeg_path()
    if not ff:
        return _probe_av(path, info)
    r = subprocess.run([ff, "-hide_banner", "-i", path], capture_output=True, text=True, encoding="utf-8", errors="replace")
    err = r.stderr
    m = re.search(r"Duration:\s*(\d+:\d+:\d+(?:\.\d+)?)", err)
    if m:
        info["duration"] = _hms(m.group(1))
    v = re.search(r"Stream #\S+.*?Video:.*?(\d{2,5})x(\d{2,5})", err)
    if v:
        info.update(has_video=True, width=int(v.group(1)), height=int(v.group(2)))
        f = re.search(r"Video:.*?([\d.]+) fps", err)
        if f:
            info["fps"] = float(f.group(1))
    info["has_audio"] = bool(re.search(r"Stream #\S+.*?Audio:", err))
    return info


def _probe_av(path: str, info: dict) -> dict:
    """ffmpeg가 없을 때 PyAV(faster-whisper에 포함)로 정보를 읽는다."""
    try:
        import av  # type: ignore
        with av.open(path) as c:
            if c.duration:
                info["duration"] = c.duration / 1_000_000
            for s in c.streams:
                if s.type == "video" and not info["has_video"]:
                    info.update(has_video=True, width=s.codec_context.width, height=s.codec_context.height,
                                fps=float(s.average_rate or 0))
                elif s.type == "audio":
                    info["has_audio"] = True
    except Exception:  # noqa: BLE001 — av가 없거나 파일을 못 읽으면 기본값
        pass
    return info


def filter_path(p: str) -> str:
    """ffmpeg 필터 옵션 값(작은따옴표 안)에 넣는 경로. Windows 'C:\\a\\b.ass' → 'C\\:/a/b.ass'.
    작은따옴표는 따옴표를 닫고 \\'를 넣은 뒤 다시 연다('\\'')."""
    p = str(p).replace("\\", "/").replace(":", "\\:")
    return p.replace("'", "'\\''")


def frame_luma(path: str, t: float) -> float | None:
    """t초 프레임의 평균 밝기(0~255). 검은 화면 검사용. 실패하면 None."""
    ff = ffmpeg_path()
    if not ff:
        return None
    r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-ss", f"{max(t, 0):.2f}", "-i", path, "-frames:v", "1",
                        "-vf", "scale=64:-2,format=gray", "-f", "rawvideo", "-"], capture_output=True)
    if r.returncode != 0 or not r.stdout:
        return None
    data = r.stdout
    return sum(data) / len(data)


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    if argv[:1] == ["--probe"] and len(argv) > 1:
        print(json.dumps(probe(argv[1]), ensure_ascii=False))
        return 0
    ff = ffmpeg_path()
    if not ff:
        print("FFMPEG MISSING — 설치: winget install Gyan.FFmpeg 또는 pip install imageio-ffmpeg")
        return 1
    ver = subprocess.run([ff, "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    print(f"ffmpeg: {ff}\n{ver}\nffprobe: {ffprobe_path() or '없음(ffmpeg -i로 대체)'}")
    print("FFMPEG OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
