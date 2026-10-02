#!/usr/bin/env python3
"""
YouTube 자체 자막 추출
- 수동자막 우선, 없으면 자동생성 자막 사용
- 권리를 가진 영상(내 채널·허락받은 영상)만. 브라우저 쿠키는 자동으로 쓰지 않는다
  (YT_COOKIE_FILE·YT_COOKIE_BROWSER를 사용자가 직접 설정한 경우만)
- 에러 발생 시 output/logs/에 상세 로그 저장
"""

import argparse
import json
import os
import re
import subprocess
import sys


# --- yt-dlp 설정 ---

MAX_RETRIES = 2


def get_cookie_args() -> list:
    f = os.environ.get("YT_COOKIE_FILE")
    if f and os.path.isfile(f):
        return ["--cookies", f]
    b = os.environ.get("YT_COOKIE_BROWSER")
    return ["--cookies-from-browser", b] if b else []


def log_error(description: str, cmd: list, result) -> str:
    """에러 로그를 output/logs/에 저장하고 경로 반환"""
    log_dir = "output/logs"
    os.makedirs(log_dir, exist_ok=True)
    safe_desc = re.sub(r'[^\w\-]', '_', description)
    log_path = os.path.join(log_dir, f"error_{safe_desc}.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"CMD: {' '.join(cmd)}\n\n")
        f.write(f"RETURNCODE: {result.returncode}\n\n")
        f.write(f"STDOUT:\n{result.stdout}\n\n")
        f.write(f"STDERR:\n{result.stderr}\n")
    return log_path


def build_ytdlp_base_args(use_cookies: bool = False) -> list:
    """yt-dlp 공통 인자(python -m yt_dlp). use_cookies는 호환용 인자이며 쿠키는 사용자가 설정한 경우만 쓴다."""
    args = [sys.executable, "-m", "yt_dlp", *get_cookie_args()]
    proxy = os.environ.get("YT_PROXY")  # 회사 네트워크 프록시가 필요한 경우
    if proxy:
        args.extend(["--proxy", proxy])
    return args


def extract_subtitles(url: str, output_dir: str, lang: str = "ko") -> str | None:
    """YouTube 자막 추출 (수동 -> 자동 -> 아무 언어)"""
    os.makedirs(output_dir, exist_ok=True)

    # 1차: 수동 자막
    print(f"[1/3] 수동 자막 추출 시도 (lang={lang})...")
    srt_path = _try_download_subs(url, output_dir, lang, auto=False)
    if srt_path:
        print(f"  수동 자막 발견: {srt_path}")
        return srt_path

    # 2차: 자동생성 자막
    print(f"[2/3] 자동생성 자막 추출 시도...")
    srt_path = _try_download_subs(url, output_dir, lang, auto=True)
    if srt_path:
        print(f"  자동 자막 발견: {srt_path}")
        return srt_path

    # 3차: 아무 언어
    print(f"[3/3] 사용 가능한 자막 탐색...")
    srt_path = _try_any_language(url, output_dir)
    if srt_path:
        print(f"  대체 자막 발견: {srt_path}")
    else:
        print("  자막을 찾을 수 없습니다.")

    return srt_path


BLOCKED = ("sign in", "bot", "po token", "confirm you")


def _blocked_hint() -> None:
    print("  YouTube가 로그인 확인을 요구한다. 내 영상이면 YouTube Studio에서 영상·자막을 내려받아 --video·--subs로 진행한다")


def _try_download_subs(url: str, output_dir: str, lang: str, auto: bool) -> str | None:
    """자막 다운로드(수동 또는 자동). 쿠키는 사용자가 설정한 경우만 쓴다."""
    prefix = "auto_sub" if auto else "manual_sub"
    for attempt in range(MAX_RETRIES):
        try:
            cmd = build_ytdlp_base_args() + (["--write-auto-sub"] if auto else ["--write-sub"]) + [
                "--sub-lang", lang, "--skip-download", "--convert-subs", "srt",
                "-o", os.path.join(output_dir, prefix), url]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            srt_path = _find_srt(output_dir, prefix)  # returncode와 무관하게 파일이 생겼을 수 있다
            if srt_path:
                return srt_path
            if result.returncode != 0:
                log_error(f"subtitle_{prefix}_attempt{attempt}", cmd, result)
                if any(k in result.stderr.lower() for k in BLOCKED):
                    _blocked_hint()
                    return None
        except subprocess.TimeoutExpired:
            print(f"  타임아웃 (시도 {attempt + 1})")
        except Exception as e:  # noqa: BLE001
            print(f"  오류: {e}")
    return None


def _try_any_language(url: str, output_dir: str) -> str | None:
    """사용 가능한 아무 자막이나 추출"""
    try:
        cmd = build_ytdlp_base_args() + ["--list-subs", "--skip-download", url]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        if result.returncode != 0:
            log_error("list_subs", cmd, result)
            if any(k in result.stderr.lower() for k in BLOCKED):
                _blocked_hint()
            return None
        langs = _parse_available_langs(result.stdout)
        if not langs:
            return None
        target = next((p for p in ("ko", "en") if p in langs), langs[0])
        print(f"  사용 가능: {', '.join(langs[:5])}... -> {target} 선택")
        cmd = build_ytdlp_base_args() + ["--write-auto-sub", "--write-sub", "--sub-lang", target, "--skip-download",
                                         "--convert-subs", "srt", "-o", os.path.join(output_dir, "any_sub"), url]
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        return _find_srt(output_dir, "any_sub")
    except Exception as e:  # noqa: BLE001
        print(f"  오류: {e}")
    return None


def _find_srt(directory: str, prefix: str) -> str | None:
    for f in os.listdir(directory):
        if f.startswith(prefix) and f.endswith(".srt"):
            return os.path.join(directory, f)
    return None


def _parse_available_langs(stdout: str) -> list:
    langs = []
    in_table = False
    for line in stdout.split("\n"):
        line = line.strip()
        if "Language" in line and ("Name" in line or "Formats" in line):
            in_table = True
            continue
        if in_table and line:
            parts = line.split()
            if parts and re.match(r'^[a-z]{2}(-[a-zA-Z]+)?$', parts[0]):
                langs.append(parts[0])
    return langs


def parse_srt_to_transcript(srt_path: str) -> dict:
    """SRT -> transcript JSON (중복 제거, HTML 태그 제거)"""
    chunks = []
    full_text = []

    with open(srt_path, "r", encoding="utf-8-sig") as f:
        content = f.read().replace("\r\n", "\n")  # Windows에서 만든 CRLF 자막도 블록으로 나뉘게

    blocks = re.split(r"\n\s*\n", content.strip())
    prev_text = ""

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue

        time_line = lines[1]
        text = " ".join(lines[2:]).strip()
        text = re.sub(r'<[^>]+>', '', text).strip()

        if not text or text == prev_text:
            continue
        if " --> " not in time_line:
            continue

        start_str, end_str = time_line.split(" --> ")
        start = _parse_srt_time(start_str.strip())
        end = _parse_srt_time(end_str.strip())

        chunks.append({
            "text": text,
            "timestamp": [round(start, 2), round(end, 2)]
        })
        full_text.append(text)
        prev_text = text

    return {"text": " ".join(full_text), "chunks": chunks}


def _parse_srt_time(time_str: str) -> float:
    time_str = time_str.replace(",", ".")
    parts = time_str.split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


def _fmt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_clean_srt(chunks: list) -> str:
    lines = []
    for i, chunk in enumerate(chunks, 1):
        start, end = chunk["timestamp"]
        text = chunk["text"].strip()
        if not text:
            continue
        lines.append(str(i))
        lines.append(f"{_fmt_time(start)} --> {_fmt_time(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def to_timestamped_text(chunks: list) -> str:
    lines = []
    for chunk in chunks:
        start, end = chunk["timestamp"]
        text = chunk["text"].strip()
        if text:
            lines.append(f"[{start:.1f}s - {end:.1f}s] {text}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="YouTube 자막 추출")
    parser.add_argument("--url", required=True, help="YouTube URL")
    parser.add_argument("--output", required=True, help="출력 디렉토리")
    parser.add_argument("--lang", default="ko", help="자막 언어 (기본: ko)")
    args = parser.parse_args()

    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs("output/logs", exist_ok=True)

    print(f"=== YouTube 자막 추출 ===")
    print(f"URL: {args.url}")
    print(f"언어: {args.lang}")
    print(f"쿠키: {'사용자 설정 사용' if get_cookie_args() else '사용 안 함'}")
    print()

    srt_path = extract_subtitles(args.url, output_dir, args.lang)

    if not srt_path:
        print("\nERROR: 자막을 추출할 수 없습니다.")
        print("가능한 원인:")
        print("  - 해당 영상에 자막이 없음")
        print("  - YouTube 로그인 확인 요구 -> 내 영상이면 YouTube Studio에서 영상·자막을 받아 로컬 파일로 진행")
        print("  - 회사 네트워크 -> YT_PROXY 설정 확인")
        print("  - 상세 로그: output/logs/")
        sys.exit(1)

    print("\n자막 파싱 중...")
    transcript = parse_srt_to_transcript(srt_path)
    chunks = transcript.get("chunks", [])

    if not chunks:
        print("ERROR: 자막 파싱 결과가 비어있습니다.")
        sys.exit(1)

    json_path = os.path.join(output_dir, "transcript.json")
    clean_srt_path = os.path.join(output_dir, "transcript.srt")
    txt_path = os.path.join(output_dir, "transcript_timestamped.txt")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, ensure_ascii=False, indent=2)
    with open(clean_srt_path, "w", encoding="utf-8") as f:
        f.write(to_clean_srt(chunks))
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(to_timestamped_text(chunks))

    if srt_path != clean_srt_path and os.path.exists(srt_path):
        # 정리 실패(파일 잠금 등)는 치명적이지 않으므로 전체 실행을 죽이지 않는다
        try:
            os.remove(srt_path)
        except OSError as e:
            print(f"경고: 임시 자막 파일 정리 실패 (무시): {e}")

    total_duration = chunks[-1]["timestamp"][1] if chunks else 0
    print(f"\n=== 자막 추출 완료 ===")
    print(f"세그먼트: {len(chunks)}개")
    print(f"총 길이: {total_duration:.0f}초 ({total_duration / 60:.1f}분)")
    print(f"JSON: {json_path}")
    print(f"SRT:  {clean_srt_path}")
    print(f"TXT:  {txt_path}")


if __name__ == "__main__":
    main()
