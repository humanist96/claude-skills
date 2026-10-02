#!/usr/bin/env python3
"""
쇼츠 영상 자동 편집
- 입력: 로컬 영상(--video, 권장) 또는 권리를 확인한 YouTube URL(--url, 하이라이트 구간만 받음)
- ffmpeg는 scripts/_vendor/media.py가 찾는다(PATH·FFMPEG_BINARY·imageio-ffmpeg). ffprobe 없어도 된다
- 한글 폰트는 scripts/_vendor/fonts.py가 찾는다(Windows 맑은 고딕 포함)
- 브라우저 쿠키는 자동으로 쓰지 않는다(YT_COOKIE_FILE·YT_COOKIE_BROWSER를 직접 설정한 경우만)
- 에러 발생 시 output/logs/에 상세 로그
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "_vendor"))
from media import filter_path, probe, require_ffmpeg  # noqa: E402
from fonts import family_for, find_font  # noqa: E402


# --- YouTube(권리를 가진 영상만) ---

MAX_RETRIES = 2


def get_cookie_args() -> list:
    """브라우저 쿠키는 자동으로 쓰지 않는다. 사용자가 직접 설정한 경우만:
    YT_COOKIE_FILE=쿠키 파일 경로, 또는 YT_COOKIE_BROWSER=브라우저 이름."""
    f = os.environ.get("YT_COOKIE_FILE")
    if f and os.path.isfile(f):
        return ["--cookies", f]
    b = os.environ.get("YT_COOKIE_BROWSER")
    return ["--cookies-from-browser", b] if b else []


def build_ytdlp_base_args() -> list:
    """yt-dlp 공통 인자(python -m yt_dlp — 실행 파일이 PATH에 없어도 된다)."""
    args = [sys.executable, "-m", "yt_dlp", *get_cookie_args()]
    proxy = os.environ.get("YT_PROXY")  # 회사 네트워크 프록시가 필요한 경우
    if proxy:
        args.extend(["--proxy", proxy])
    return args


# --- 한글 폰트 ---

def get_font_path() -> str | None:
    """한글 지원 폰트 경로(굵은 글꼴 우선). Windows·macOS·Linux 공통 탐색은 fonts.py."""
    return find_font("bold") or find_font()


def _filter_path(p: str) -> str:
    """ffmpeg 필터 옵션 값(작은따옴표 안)용 경로 이스케이프(Windows 'C:\\…' 포함). media.filter_path."""
    return filter_path(p)


# --- 에러 로깅 ---

def log_error(description: str, cmd: list, result) -> str:
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


def run_cmd(cmd: list, description: str = "", timeout: int = 120):
    """통합 명령 실행 + 에러 로깅"""
    if cmd and cmd[0] == "ffmpeg":
        cmd = [require_ffmpeg(), *cmd[1:]]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        if result.returncode != 0:
            log_path = log_error(description, cmd, result)
            print(f"    {description} 실패 - 로그: {log_path}")
        return result
    except subprocess.TimeoutExpired:
        print(f"    {description} 타임아웃 ({timeout}초)")
        return None


# --- 영상 정보 ---

def get_video_info(video_path: str) -> dict:
    """영상의 해상도, fps 정보 추출(ffprobe가 없으면 ffmpeg -i로)."""
    info = probe(video_path)
    return {"width": info["width"] or 1080, "height": info["height"] or 1920, "fps": info["fps"] or 30}


def has_audio_stream(video_path: str) -> bool:
    """영상에 오디오 스트림이 있는지 확인 (concat 조립 전 필수 체크)"""
    return probe(video_path)["has_audio"]


def get_duration(video_path: str) -> float:
    return probe(video_path)["duration"]


# --- 다운로드 ---

def cut_local_section(video: str, start: float, end: float, output_path: str) -> bool:
    """로컬 영상에서 구간을 잘라 낸다(정확한 경계를 위해 다시 인코딩)."""
    cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", video, "-t", f"{end - start:.3f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "160k", output_path]
    result = run_cmd(cmd, f"cut_s{start:.0f}_e{end:.0f}", timeout=300)
    if result is not None and result.returncode == 0 and get_duration(output_path) > 0:
        return True
    if os.path.exists(output_path):
        os.remove(output_path)
    return False


def download_section(url: str, start: float, end: float, output_path: str) -> bool:
    """YouTube 구간 다운로드(권리를 가진 영상만). 실패하면 로컬 파일로 진행하도록 안내한다."""
    section_spec = f"*{start}-{end}"
    for attempt in range(MAX_RETRIES):
        if attempt > 0:
            print(f"    재시도 {attempt + 1}/{MAX_RETRIES}...")
            time.sleep(3)
        cmd = build_ytdlp_base_args() + [
            "--download-sections", section_spec,
            "-f", "bestvideo[height<=1080]+bestaudio/best",
            "--merge-output-format", "mp4",
            "-o", output_path,
            "--force-keyframes-at-cuts",
            url
        ]
        result = run_cmd(cmd, f"download_s{start:.0f}_e{end:.0f}", timeout=180)
        if result is None:
            continue
        # 손상/부분 파일이 영구 캐시로 승격되면 이후 모든 인코딩이 반복 실패한다
        if os.path.exists(output_path):
            if get_duration(output_path) > 0:
                return True
            os.remove(output_path)
        # yt-dlp가 다른 이름으로 저장했을 수 있음. .part/.ytdl 같은 미완성 임시 파일은 승격하지 않는다
        base = os.path.splitext(output_path)[0]
        candidates = [c for c in glob.glob(f"{base}*") if not c.endswith((".part", ".ytdl", ".temp"))]
        if candidates:
            os.rename(candidates[0], output_path)
            if get_duration(output_path) > 0:
                return True
            os.remove(output_path)
        if result.returncode != 0:
            err = result.stderr.lower()
            if "sign in" in err or "bot" in err:
                print("    YouTube가 로그인 확인을 요구한다. 내 영상이면 YouTube Studio에서 원본을 내려받아 --video로 진행한다")
                return False
    return False


def acquire_section(source: dict, start: float, end: float, output_path: str) -> bool:
    if source.get("video"):
        return cut_local_section(source["video"], start, end, output_path)
    return download_section(source["url"], start, end, output_path)


def source_key(source: dict) -> str:
    if source.get("video"):
        return re.sub(r"[^A-Za-z0-9_-]", "", Path(source["video"]).stem)[:16] or "local"
    return _video_id(source["url"])


def _video_id(url: str) -> str:
    """캐시 키용 영상 식별자. 같은 캐시 디렉토리를 다른 영상이 공유할 때
    이전 영상의 구간을 재사용하는 사고를 막는다."""
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{6,})", url or "")
    if m:
        return m.group(1)[:16]
    fallback = re.sub(r"[^A-Za-z0-9_-]", "", url or "")
    return (fallback[-12:] or "local")


# --- 자막 추출 ---

def extract_srt_for_section(full_srt_path: str, start: float, end: float, output_srt: str):
    """전체 SRT에서 구간 자막 추출 + offset 조정"""
    if not os.path.exists(full_srt_path):
        with open(output_srt, "w", encoding="utf-8") as f:
            f.write("")
        return

    with open(full_srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = content.strip().split("\n\n")
    filtered = []
    idx = 1

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        time_line = lines[1]
        if " --> " not in time_line:
            continue

        start_str, end_str = time_line.split(" --> ")
        seg_start = _parse_srt_time(start_str.strip())
        seg_end = _parse_srt_time(end_str.strip())

        if seg_end > start and seg_start < end:
            adj_start = max(0, seg_start - start)
            adj_end = seg_end - start
            text = "\n".join(lines[2:])
            filtered.append(f"{idx}\n{_fmt_time(adj_start)} --> {_fmt_time(adj_end)}\n{text}")
            idx += 1

    with open(output_srt, "w", encoding="utf-8") as f:
        f.write("\n\n".join(filtered))


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


# --- 자막(ASS) 생성 ---

def _sec_to_ass(t: float) -> str:
    """초(float) -> ASS 시간(0:01:02.34)"""
    t = max(0.0, float(t))
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = min(int(round((t - int(t)) * 100)), 99)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def write_ass(
    events: list, ass_path: str, font_name: str, font_size: int,
    width: int, height: int, margin_v: int, outline: int
) -> int:
    """자막 이벤트 [(시작초, 끝초, 텍스트), ...] 를 ASS 자막 파일로 쓴다.

    핵심: ffmpeg의 subtitles(SRT) 필터는 PlayRes를 기본 384x288로 잡아서
    FontSize를 최종 프레임(1080x1920)에 맞춰 6배 이상 확대해 버린다(자막이 화면을 덮음).
    ASS를 직접 만들어 PlayResX/Y를 실제 해상도로 지정하면 FontSize가 실제 픽셀이 되어
    자막 크기가 환경과 무관하게 예측 가능해진다.
    이벤트 시간은 영상 시작 기준 상대 초. 반환: 기록된 이벤트 수.
    """
    valid = []
    for start, end, text in events:
        # ASS 오버라이드 블록으로 오인되지 않도록 중괄호 치환
        text = str(text).replace("{", "(").replace("}", ")").replace("\r", "").strip()
        # 리터럴 개행은 ASS 줄바꿈(\N)으로 — 그대로 두면 Dialogue 줄이 쪼개져 뒷줄이 조용히 사라진다
        text = text.replace("\n", "\\N")
        try:
            start_f, end_f = float(start), float(end)
        except (TypeError, ValueError):
            continue
        if text and end_f > start_f:
            valid.append((start_f, end_f, text))

    fn = font_name or "Sans"
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 0\n"  # 0 = 긴 줄 자동 줄바꿈(좌우 여백 안에서). 2는 자동 줄바꿈이 없어 화면 밖으로 넘친다.
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{fn},{font_size},&H00FFFFFF,&H00000000,&H64000000,"
        f"0,0,0,0,100,100,0,0,3,{outline},0,2,60,60,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header)
        for start, end, text in valid:
            f.write(f"Dialogue: 0,{_sec_to_ass(start)},{_sec_to_ass(end)},Default,,0,0,0,,{text}\n")
    return len(valid)


def write_ass_from_srt(
    srt_path: str, ass_path: str, font_name: str, font_size: int,
    width: int, height: int, margin_v: int, outline: int
) -> int:
    """구간 SRT를 ASS로 변환한다 (Claude 재구성 자막이 없을 때의 폴백)."""
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    events = []
    for block in content.strip().split("\n\n"):
        lines = block.strip().split("\n")
        if len(lines) < 3 or " --> " not in lines[1]:
            continue
        start_str, end_str = lines[1].split(" --> ")
        text = "\\N".join(ln.strip() for ln in lines[2:] if ln.strip())
        if text:
            events.append((_parse_srt_time(start_str.strip()), _parse_srt_time(end_str.strip()), text))

    return write_ass(events, ass_path, font_name, font_size, width, height, margin_v, outline)


# --- 텍스트 오버레이 (인트로/아웃트로) ---

def write_drawtext_file(path: str, text: str) -> None:
    """drawtext textfile을 LF 줄바꿈으로 쓴다. Windows 텍스트 모드(CRLF)로 쓰면 drawtext가 CR도
    줄바꿈으로 읽어 줄 사이에 빈 줄이 생긴다(두 줄 후크의 간격이 세 배)."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def wrap_text(text: str, max_chars: int = 11, max_lines: int = 4) -> str:
    """인트로/아웃트로 카드 텍스트를 줄바꿈한다.
    drawtext는 자동 줄바꿈이 없어, 긴 문장을 그대로 넣으면 한 줄로 화면 밖까지 넘친다.
    """
    text = (text or "").strip()
    if not text:
        return ""
    lines, cur = [], ""
    for word in text.split():
        cand = (cur + " " + word).strip()
        if len(cand) <= max_chars:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        # 한 단어가 너무 길면 강제로 자른다
        while len(word) > max_chars:
            lines.append(word[:max_chars])
            word = word[max_chars:]
        cur = word
    if cur:
        lines.append(cur)
    return "\n".join(lines[:max_lines])


def create_text_overlay(
    text: str, duration: float, width: int, height: int,
    output_path: str, font_size: int = 48, fps: float = 30,
    bg_color: str = "black"
):
    """텍스트 오버레이 영상 (한글 폰트 지정, 자동 줄바꿈, fps 맞춤).
    텍스트는 textfile로 전달해 따옴표/콜론 이스케이프 문제를 피하고, 여러 줄을 지원한다.
    """
    font_path = get_font_path()
    fontfile_opt = f":fontfile='{_filter_path(font_path)}'" if font_path else ""

    txt_file = output_path + ".txt"
    write_drawtext_file(txt_file, wrap_text(text))

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c={bg_color}:s={width}x{height}:d={duration}:r={fps}",
        "-f", "lavfi",
        "-i", f"anullsrc=r=48000:cl=stereo",
        "-t", str(duration),
        "-vf", (
            f"drawtext=textfile='{_filter_path(txt_file)}':"
            f"fontsize={font_size}:fontcolor=white:"
            f"x=(w-text_w)/2:y=(h-text_h)/2:"
            # expansion=none: 텍스트에 %가 있으면 기본 expansion이 렌더링을 통째로 삼킨다
            f"line_spacing=18:borderw=4:bordercolor=black:expansion=none"
            f"{fontfile_opt}"
        ),
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac",
        "-shortest",
        output_path
    ]
    result = run_cmd(cmd, f"overlay_{os.path.basename(output_path)}")
    return result is not None and result.returncode == 0


# --- 후크 오버레이 ---

def build_hook_drawtext(hook_txt_path: str, font_path, font_size: int, duration: float) -> str:
    """본편 첫 부분 위에 얹는 후크 텍스트 필터를 만든다.

    검은 인트로 카드 대신 쓰는 이유: 쇼츠의 첫 1~2초가 정지된 검은 화면이면
    시청자가 내용을 보기도 전에 스와이프한다. 본편을 즉시 보여주면서 그 위에
    후크 문구를 얹어야 이탈 없이 관심을 끌 수 있다.
    """
    fontfile_opt = f":fontfile='{_filter_path(font_path)}'" if font_path else ""
    return (
        f"drawtext=textfile='{_filter_path(hook_txt_path)}':"
        f"fontsize={font_size}:fontcolor=white:"
        f"x=(w-text_w)/2:y=h*0.14:"
        f"line_spacing=14:"
        f"box=1:boxcolor=black@0.45:boxborderw=22:"
        # expansion=none: 텍스트에 %가 있으면 기본 expansion이 렌더링을 통째로 삼킨다
        f"expansion=none:"
        f"enable='between(t,0,{duration})'"
        f"{fontfile_opt}"
    )


# --- 세로 레이아웃 (16:9 -> 9:16 변환) ---

def build_layout_filtergraph(
    layout: str, width: int, height: int,
    blur_radius: int, post_filters: str
) -> str:
    """
    원본을 세로(width x height)로 변환하는 filter_complex 문자열을 만든다.
    반환 그래프는 [0:v]를 입력으로 받아 [outv]를 출력한다.

    핵심: 원본이 16:9 가로 영상일 때 세로로 바꾸는 방식이 결과 품질을 좌우한다.
    화면 녹화/코드/슬라이드처럼 가장자리 정보가 중요한 영상을 crop으로 처리하면
    좌우가 잘려 글자를 못 읽게 된다. 그래서 기본값은 잘라내지 않는 fit_blur이다.

    layout:
      - "fit_blur" (기본): 원본 전체를 폭에 맞춰 넣고 위아래 여백을 같은 화면의
        블러 확대본으로 채운다. 화면 어디도 잘리지 않아 화면 녹화/코드/슬라이드/
        강의/게임 등 가장자리 정보가 중요한 영상에 안전하다. ("auto"도 여기로.)
      - "fit": 블러 없이 단색(검정) 레터박스. 배경을 깔끔하게 두고 싶을 때.
      - "crop": 가운데를 꽉 채우고 좌우를 잘라낸다. 인물이 화면 중앙에 있는
        토킹헤드/인터뷰/브이로그처럼 "가운데만 중요한" 영상에만 적합하다.

    post_filters: 레이아웃 뒤에 이어붙일 필터 체인(자막 ass=..., 후크 drawtext=... 등,
                  콤마로 연결, 앞 콤마 없이). 없으면 빈 문자열.
    """
    sub = f",{post_filters}" if post_filters else ""

    if layout == "crop":
        return (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}{sub}[outv]"
        )
    if layout == "fit":
        return (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black{sub}[outv]"
        )
    # fit_blur (기본값, "auto" 포함): 잘라내지 않는 안전한 방식
    return (
        f"[0:v]split=2[bg][fg];"
        f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},boxblur={blur_radius}:1[bgb];"
        f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2{sub}[outv]"
    )


def make_hashtag(text: str) -> str:
    """안전한 해시태그 하나(특수문자·공백 제거, 20자 이내)."""
    tag = re.sub(r"[^0-9A-Za-z가-힣]", "", text or "")[:20]
    return f"#{tag}" if tag else ""


def make_hashtags(highlight: dict, title: str) -> list[str]:
    """#shorts #쇼츠 + 주제 태그. highlights.json의 hashtags(Claude가 고른 단어)를 우선 쓰고,
    없으면 제목의 첫 단어 하나만 쓴다(제목 전체를 붙인 긴 태그는 검색에 쓸모가 없다)."""
    picked = highlight.get("hashtags")
    if isinstance(picked, list) and picked:
        topic = [make_hashtag(str(x)) for x in picked]
    else:
        words = [w for w in re.split(r"\s+", re.sub(r"[^0-9A-Za-z가-힣\s]", " ", title or "")) if len(w) >= 2]
        topic = [make_hashtag(words[0])] if words else []
    out = ["#shorts", "#쇼츠"]
    for tag in topic:
        if tag and tag not in out:
            out.append(tag)
    return out


# --- 쇼츠 처리 ---

def process_short(
    index: int, highlight: dict, source: dict,
    output_dir: str, srt_path: str, config: dict
) -> dict | None:
    """단일 쇼츠 영상 처리"""
    start = highlight["start"]
    end = highlight["end"]
    title = highlight.get("title", f"Short {index}")
    hook = highlight.get("hook", "")
    duration = end - start

    print(f"\n--- Short {index:02d}: {title} [{start:.1f}s - {end:.1f}s] ({duration:.0f}s) ---")

    cache_dir = config.get("cache_dir", "")
    # 캐시 키 = 영상ID + 번호 + 구간 경계.
    # 경계가 빠지면 highlights 수정 후 stale 구간을 재사용하고,
    # 영상ID가 빠지면 다른 영상의 구간을 재사용하는 사고가 난다.
    cached = (os.path.join(cache_dir, f"seg_{source_key(source)}_{index:02d}_{start:.1f}-{end:.1f}.mp4")
              if cache_dir else None)

    width = config.get("width", 1080)
    height = config.get("height", 1920)
    intro_duration = config.get("intro_duration", 2)
    outro_duration = config.get("outro_duration", 2)
    outro_text = config.get("outro_text", "구독과 좋아요 부탁드립니다!")
    font_size = config.get("subtitle_font_size", 54)
    border_width = config.get("subtitle_border_width", 3)
    subtitle_margin_v = config.get("subtitle_margin_v", 150)
    layout = config.get("layout", "fit_blur")
    blur_radius = config.get("bg_blur_radius", 20)
    hook_overlay = bool(config.get("hook_overlay", True))
    hook_duration = float(config.get("hook_duration", 2.5))
    hook_font_size = int(config.get("hook_font_size", 64))
    use_intro_card = bool(config.get("intro_card", False))
    use_outro = bool(config.get("outro_enabled", False))

    font_path = get_font_path()

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_path = os.path.join(tmpdir, f"raw_{index:02d}.mp4")
        # SRT를 심플한 이름으로 (문제 9: 특수문자 방지)
        section_srt = os.path.join(tmpdir, f"sub.srt")
        cropped_path = os.path.join(tmpdir, f"cropped.mp4")
        intro_path = os.path.join(tmpdir, f"intro.mp4")
        outro_path = os.path.join(tmpdir, f"outro.mp4")
        final_path = os.path.join(output_dir, f"short_{index:02d}.mp4")

        # 1. 구간 확보 — 캐시 우선 (재실행/시간 제한 환경에서 재다운로드 방지)
        if cached and os.path.exists(cached) and os.path.getsize(cached) > 0 and get_duration(cached) > 0:
            print(f"  1/4 캐시된 구간 사용 ({os.path.basename(cached)})...")
            shutil.copy2(cached, raw_path)
        else:
            print(f"  1/4 구간 {'자르는' if source.get('video') else '다운로드'} 중...")
            if not acquire_section(source, start, end, raw_path):
                print(f"  건너뜀: 구간 확보 실패")
                return None
            if cached:
                os.makedirs(cache_dir, exist_ok=True)
                shutil.copy2(raw_path, cached)

        # 본편 영상 정보 추출 (문제 8: fps 맞춤)
        video_info = get_video_info(raw_path)
        fps = video_info["fps"]

        # 2. 자막 준비 — Claude가 재구성한 자막(highlights.json의 subtitles)이 있으면 우선 사용
        print(f"  2/4 자막 준비 중...")
        # libass는 글꼴을 family 이름으로 찾는다(파일 이름 'malgunbd'가 아니라 'Malgun Gothic').
        font_name = (family_for(font_path) or os.path.splitext(os.path.basename(font_path))[0]) if font_path else ""
        ass_path = os.path.join(tmpdir, "sub.ass")
        n_events = 0
        curated_subs = highlight.get("subtitles")
        if curated_subs:
            events = []
            for s in curated_subs:
                try:
                    events.append((float(s["start"]), float(s["end"]), str(s["text"])))
                except (KeyError, TypeError, ValueError):
                    continue
            n_events = write_ass(events, ass_path, font_name, font_size,
                                 width, height, subtitle_margin_v, border_width)
            print(f"    재구성 자막 {n_events}개 사용 (Claude 큐레이션)")
        elif curated_subs is not None:
            # 명시적 빈 배열([]) = 자막을 의도적으로 생략 (원본에 자막이 구워진 영상 등)
            print(f"    자막 생략 (subtitles: [])")
        else:
            # 필드 없음 → 폴백: 원본 자동자막을 구간만 잘라 사용 (롤링 파편 그대로라 품질 낮음)
            extract_srt_for_section(srt_path, start, end, section_srt)
            if os.path.exists(section_srt) and os.path.getsize(section_srt) > 0:
                n_events = write_ass_from_srt(section_srt, ass_path, font_name, font_size,
                                              width, height, subtitle_margin_v, border_width)

        # 3. 세로 레이아웃 + 자막 + 후크 오버레이
        print(f"  3/4 세로 레이아웃({layout}) + 자막/후크 합성 중...")
        post_parts = []
        if n_events > 0:
            fontsdir = f":fontsdir='{_filter_path(os.path.dirname(font_path))}'" if font_path else ""
            post_parts.append(f"ass='{_filter_path(ass_path)}'{fontsdir}")

        hook_text = (hook or title or "").strip()
        if hook_overlay and hook_text:
            hook_txt_path = os.path.join(tmpdir, "hook.txt")
            write_drawtext_file(hook_txt_path, wrap_text(hook_text, max_chars=12, max_lines=3))
            post_parts.append(build_hook_drawtext(hook_txt_path, font_path, hook_font_size, hook_duration))

        def _run_layout(post: str, tag: str):
            filtergraph = build_layout_filtergraph(layout, width, height, blur_radius, post)
            cmd = [
                "ffmpeg", "-y", "-i", raw_path,
                "-filter_complex", filtergraph,
                "-map", "[outv]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                cropped_path
            ]
            return run_cmd(cmd, tag)

        result = _run_layout(",".join(post_parts), f"layout_short{index:02d}")
        overlay_ok = True
        if (result is None or result.returncode != 0) and post_parts:
            # 메모리 부족 같은 일시 오류가 많으므로 같은 합성을 한 번 더 해 본다
            print(f"    자막/후크 합성 실패, 한 번 더 시도...")
            result = _run_layout(",".join(post_parts), f"layout_retry_short{index:02d}")

        if result is None or result.returncode != 0:
            # 그래도 실패하면 레이아웃만으로 만들되, 성공으로 숨기지 않고 metadata에 overlay=false로 남긴다
            overlay_ok = not post_parts
            print(f"    경고: 자막/후크 합성 실패 — 오버레이 없이 만든다(완성 검사에서 오류로 잡힌다)")
            retry = _run_layout("", f"layout_nosub_short{index:02d}")
            if retry is None or retry.returncode != 0:
                # ffmpeg -y는 실패해도 부분 파일을 남기므로, 지워서 성공으로 오인되지 않게 한다
                if os.path.exists(cropped_path):
                    os.remove(cropped_path)

        if not os.path.exists(cropped_path):
            print(f"  건너뜀: 크롭 실패")
            return None

        # 4. (옵션) 인트로/아웃트로 카드 — 기본 꺼짐.
        # 검은 정지 카드가 앞에 붙으면 첫 1초에 시청자가 이탈하므로,
        # 기본값은 카드 없이 본편 위 후크 오버레이만 쓴다 (3단계에서 이미 합성됨).
        intro_ok = False
        outro_ok = False
        if use_intro_card:
            intro_text = title if title else hook
            intro_ok = create_text_overlay(intro_text, intro_duration, width, height, intro_path, font_size=64, fps=fps)
        if use_outro:
            outro_ok = create_text_overlay(outro_text, outro_duration, width, height, outro_path, font_size=56, fps=fps)

        if not intro_ok and not outro_ok:
            # 카드 없음(기본): 본편이 곧 최종본 (재인코딩 생략)
            print(f"  4/4 마무리 중...")
            shutil.copy2(cropped_path, final_path)
        else:
            print(f"  4/4 인트로/아웃트로 결합 중...")
            # concat filter 방식 (SAR/샘플레이트 정규화 포함)
            inputs = []
            filter_parts = []
            concat_inputs = []
            input_idx = 0

            if intro_ok and os.path.exists(intro_path):
                inputs.extend(["-i", intro_path])
                filter_parts.append(f"[{input_idx}:v:0]setsar=1[v{input_idx}];[{input_idx}:a:0]aresample=48000[a{input_idx}];")
                concat_inputs.append(f"[v{input_idx}][a{input_idx}]")
                input_idx += 1

            inputs.extend(["-i", cropped_path])
            if has_audio_stream(cropped_path):
                filter_parts.append(f"[{input_idx}:v:0]setsar=1[v{input_idx}];[{input_idx}:a:0]aresample=48000[a{input_idx}];")
                concat_inputs.append(f"[v{input_idx}][a{input_idx}]")
                input_idx += 1
            else:
                # 원본에 오디오가 없으면 [N:a:0] 참조가 concat 전체를 실패시키므로 무음 트랙을 주입한다
                vid_idx = input_idx
                aud_idx = input_idx + 1
                main_dur = get_duration(cropped_path) or (end - start)
                inputs.extend(["-f", "lavfi", "-t", f"{main_dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"])
                filter_parts.append(f"[{vid_idx}:v:0]setsar=1[v{vid_idx}];[{aud_idx}:a:0]aresample=48000[a{vid_idx}];")
                concat_inputs.append(f"[v{vid_idx}][a{vid_idx}]")
                input_idx += 2

            if outro_ok and os.path.exists(outro_path):
                inputs.extend(["-i", outro_path])
                filter_parts.append(f"[{input_idx}:v:0]setsar=1[v{input_idx}];[{input_idx}:a:0]aresample=48000[a{input_idx}];")
                concat_inputs.append(f"[v{input_idx}][a{input_idx}]")
                input_idx += 1

            n_segments = len(concat_inputs)
            filter_str = "".join(filter_parts) + "".join(concat_inputs) + f"concat=n={n_segments}:v=1:a=1[outv][outa]"

            concat_cmd = [
                "ffmpeg", "-y",
                *inputs,
                "-filter_complex", filter_str,
                "-map", "[outv]", "-map", "[outa]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                final_path
            ]
            result = run_cmd(concat_cmd, f"concat_short{index:02d}")

            # concat 실패 시 본편만 사용.
            # 주의: ffmpeg -y는 실패해도 0바이트 출력을 남기므로 존재 여부만으로 판정하면 안 된다.
            concat_failed = (result is None or result.returncode != 0)
            if concat_failed or not os.path.exists(final_path) or os.path.getsize(final_path) == 0:
                print(f"    결합 실패, 본편만 사용...")
                if os.path.exists(final_path):
                    os.remove(final_path)
                shutil.copy2(cropped_path, final_path)

        if not os.path.exists(final_path):
            print(f"  건너뜀: 최종 파일 생성 실패")
            return None

        final_size = os.path.getsize(final_path) / 1024 / 1024
        final_duration = get_duration(final_path)
        print(f"  완료: {final_path} ({final_size:.1f}MB, {final_duration:.0f}s)")

        hashtags = make_hashtags(highlight, title)

        return {
            "index": index,
            "file": f"short_{index:02d}.mp4",
            "title": title,
            "hook": hook,
            "reason": highlight.get("reason", ""),
            "duration": round(final_duration, 1),
            "size_mb": round(final_size, 1),
            "original_start": start,
            "original_end": end,
            "description": f"{hook}\n\n{' '.join(hashtags)}",
            "hashtags": hashtags,
            "overlay": overlay_ok,
        }


def main():
    parser = argparse.ArgumentParser(description="쇼츠 영상 자동 편집")
    parser.add_argument("--highlights", required=True, help="highlights.json 경로")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--video", help="원본 로컬 영상(권장)")
    src.add_argument("--url", help="권리를 확인한 YouTube URL(하이라이트 구간만 받는다)")
    parser.add_argument("--output", required=True, help="출력 디렉토리")
    parser.add_argument("--srt", default="", help="전체 SRT 자막 경로")
    parser.add_argument("--config", default="", help="config.yaml 또는 config.json 경로")
    parser.add_argument(
        "--layout", default="",
        help="세로 변환 방식: fit_blur(기본, 잘림 없음)|crop(가운데만, 좌우 잘림)|fit(단색 레터박스)"
    )
    parser.add_argument(
        "--only", default="",
        help="지정한 번호의 쇼츠만 처리 (예: 2 또는 2,3) — 명령 시간 제한이 있는 환경(코워크)용"
    )
    parser.add_argument(
        "--download-only", action="store_true",
        help="하이라이트 구간을 캐시에 다운로드만 하고 종료 (다운로드/인코딩 분리 실행용)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="이미 완성된 쇼츠도 다시 생성 (기본은 건너뜀)"
    )
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔에서 한글이 깨지지 않게
    except Exception:  # noqa: BLE001
        pass
    source = {"video": os.path.abspath(args.video)} if args.video else {"url": args.url}
    if args.video and not os.path.isfile(args.video):
        print(f"ERROR: 영상 파일이 없습니다: {args.video}")
        sys.exit(1)

    with open(args.highlights, "r", encoding="utf-8") as f:
        highlights = json.load(f)

    # 하이라이트 정규화 — 다운로드/인코딩 두 경로가 같은 규칙을 쓰도록 한 곳에서 처리.
    # (타입 오류 항목 하나가 배치 전체를 죽이거나, index 기본값이 경로마다 달라
    #  캐시 키가 어긋나는 문제를 막는다)
    normalized = []
    for pos, h in enumerate(highlights, 1):
        if not isinstance(h, dict):
            print(f"경고: 하이라이트 {pos}번이 객체가 아님 — 건너뜀")
            continue
        try:
            h["start"] = float(h["start"])
            h["end"] = float(h["end"])
        except (KeyError, TypeError, ValueError):
            print(f"경고: 하이라이트 {pos}번 start/end 형식 오류 — 건너뜀")
            continue
        if h["end"] <= h["start"]:
            print(f"경고: 하이라이트 {pos}번 구간 오류 (start >= end) — 건너뜀")
            continue
        try:
            h["index"] = int(h.get("index", pos))
        except (TypeError, ValueError):
            h["index"] = pos
        normalized.append(h)
    if not normalized:
        print("ERROR: 유효한 하이라이트가 없습니다.")
        sys.exit(1)
    highlights = normalized

    os.makedirs(args.output, exist_ok=True)
    os.makedirs("output/logs", exist_ok=True)

    srt_path = args.srt
    if not srt_path:
        srt_candidate = os.path.join(os.path.dirname(args.highlights), "transcript.srt")
        if os.path.exists(srt_candidate):
            srt_path = srt_candidate

    config = {
        "width": 1080, "height": 1920,
        "hook_overlay": True, "hook_duration": 2.5, "hook_font_size": 64,
        "intro_card": False, "outro_enabled": False,
        "intro_duration": 2, "outro_duration": 2,
        "outro_text": "구독과 좋아요 부탁드립니다!",
        "subtitle_font_size": 54,
        "subtitle_border_width": 3, "subtitle_margin_v": 150,
        "layout": "fit_blur", "bg_blur_radius": 20,
    }

    if args.config and os.path.exists(args.config):
        user_config = None
        try:
            import yaml
            with open(args.config, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f)
        except ImportError:
            # PyYAML이 없으면 JSON으로 시도
            try:
                with open(args.config, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
            except Exception:
                print(f"경고: config 파싱 실패 (JSON 아님, PyYAML 미설치) — 기본값 사용: {args.config}")
        except Exception as e:
            print(f"경고: config 파싱 실패 — 기본값 사용: {e}")
        if isinstance(user_config, dict):
            config.update(user_config)
        elif user_config is not None:
            print(f"경고: config 최상위가 매핑(dict)이 아님 — 무시: {args.config}")

    # CLI --layout 은 config 파일보다 우선한다
    if args.layout:
        config["layout"] = args.layout

    # 구간 캐시: output/shorts -> output/cache (재실행 시 재다운로드 방지).
    # --output이 "." 처럼 cwd 이상을 가리키면 부모가 작업 트리 밖이 되므로 output 내부로 고정
    out_abs = os.path.abspath(args.output)
    cwd_abs = os.path.abspath(os.getcwd())
    if out_abs == cwd_abs or cwd_abs.startswith(out_abs + os.sep):
        cache_dir = os.path.join(out_abs, "cache")
    else:
        cache_dir = os.path.join(os.path.dirname(out_abs), "cache")
    config["cache_dir"] = cache_dir

    only = set()
    if args.only:
        try:
            only = {int(x) for x in args.only.split(",") if x.strip()}
        except ValueError:
            print(f"ERROR: --only 형식 오류 (예: 2 또는 2,3): {args.only}")
            sys.exit(1)
        if not only:
            print(f"ERROR: --only에 유효한 번호가 없습니다: {args.only!r}")
            sys.exit(1)
        valid_idx = {h["index"] for h in highlights}
        if not (only & valid_idx):
            print(f"ERROR: --only {sorted(only)} 는 하이라이트에 없습니다 (있는 번호: {sorted(valid_idx)})")
            sys.exit(1)
        unknown = only - valid_idx
        if unknown:
            print(f"경고: --only 중 {sorted(unknown)} 는 하이라이트에 없어 무시됩니다")

    # 다운로드 전용 모드: 구간만 캐시에 받고 종료 (코워크처럼 명령당 시간 제한이 있는 환경에서
    # 다운로드(~20초)와 인코딩(~25초)을 별도 명령으로 나누기 위한 모드)
    if args.download_only:
        os.makedirs(cache_dir, exist_ok=True)
        print(f"=== 구간 다운로드 전용 모드 (캐시: {cache_dir}) ===")
        ok = 0
        vid = source_key(source)
        for highlight in highlights:
            idx = highlight["index"]
            if only and idx not in only:
                continue
            start, end = highlight["start"], highlight["end"]
            cached = os.path.join(cache_dir, f"seg_{vid}_{idx:02d}_{start:.1f}-{end:.1f}.mp4")
            if os.path.exists(cached) and os.path.getsize(cached) > 0 and get_duration(cached) > 0:
                print(f"[{idx:02d}] 이미 캐시됨 — 건너뜀")
                ok += 1
                continue
            print(f"[{idx:02d}] {start:.1f}s-{end:.1f}s 다운로드...")
            if acquire_section(source, start, end, cached):
                ok += 1
            else:
                print(f"[{idx:02d}] 다운로드 실패")
        print(f"완료: {ok}개 캐시됨. 이제 --only N 으로 하나씩 인코딩하세요.")
        return

    print(f"=== 쇼츠 영상 생성 ===")
    print(f"하이라이트: {len(highlights)}개")
    print(f"출력: {args.output}")
    print(f"해상도: {config['width']}x{config['height']}")
    print(f"레이아웃: {config.get('layout', 'fit_blur')}")
    font = get_font_path()
    print(f"한글 폰트: {font or '없음 (시스템 기본)'}")
    print()

    results = []
    failures = []
    for highlight in highlights:
        idx = highlight["index"]
        if only and idx not in only:
            continue

        # 재실행 안전: 이미 완성된 쇼츠는 건너뛴다 (시간 제한 환경에서 이어서 실행 가능).
        # duration 검증까지 해서 손상/부분 파일이 성공으로 오인되지 않게 한다
        final_path = os.path.join(args.output, f"short_{idx:02d}.mp4")
        if not args.force and os.path.exists(final_path) and os.path.getsize(final_path) > 0 \
                and get_duration(final_path) > 0:
            size_mb = os.path.getsize(final_path) / 1024 / 1024
            print(f"\n--- Short {idx:02d}: 이미 존재 — 건너뜀 (다시 만들려면 --force) ---")
            title = highlight.get("title", f"Short {idx}")
            hook = highlight.get("hook", "")
            hashtags = make_hashtags(highlight, title)
            results.append({
                "index": idx,
                "file": f"short_{idx:02d}.mp4",
                "title": title,
                "hook": hook,
                "reason": highlight.get("reason", ""),
                "duration": round(get_duration(final_path), 1),
                "size_mb": round(size_mb, 1),
                "original_start": highlight.get("start"),
                "original_end": highlight.get("end"),
                "description": f"{hook}\n\n{' '.join(hashtags)}",
                "hashtags": hashtags,
            })
            continue

        result = process_short(idx, highlight, source, args.output, srt_path, config)
        if result:
            results.append(result)
        else:
            failures.append({"index": idx, "title": highlight.get("title", ""), "reason": "처리 실패"})

    run_success = len(results)
    run_fail = len(failures)

    metadata_path = os.path.join(args.output, "metadata.json")
    # --only 실행 시 기존 metadata와 병합 (부분 실행이 전체 목록을 지우지 않도록).
    # 이번 실행에서 성공한 index는 기존 failures에서 빼고, 실패한 index는 기존 shorts에서 뺀다.
    if only and os.path.exists(metadata_path):
        merged, old_fail = {}, {}
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                old = json.load(f)
            merged = {s.get("index"): s for s in old.get("shorts", []) if s.get("index") is not None}
            old_fail = {x.get("index"): x for x in old.get("failures", []) if x.get("index") is not None}
        except Exception as e:
            print(f"경고: 기존 metadata.json 파싱 실패 — 이번 실행 결과만 기록합니다 ({e})")
        for r in results:
            merged[r["index"]] = r
            old_fail.pop(r["index"], None)
        for x in failures:
            old_fail[x["index"]] = x
            merged.pop(x["index"], None)
        results = [merged[k] for k in sorted(merged)]
        failures = [old_fail[k] for k in sorted(old_fail)]
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump({"shorts": results, "failures": failures}, f, ensure_ascii=False, indent=2)

    total_size = sum(r["size_mb"] for r in results)
    total_duration = sum(r["duration"] for r in results)

    print(f"\n=== 생성 완료 ===")
    scope = f" (--only {sorted(only)})" if only else ""
    print(f"이번 실행: 성공 {run_success}개 / 실패 {run_fail}개{scope}")
    print(f"전체 목록: 쇼츠 {len(results)}개")
    if failures:
        print(f"실패 목록: {len(failures)}개")
        for f_item in failures:
            print(f"  [{f_item['index']:02d}] {f_item['title']} - {f_item['reason']}")
    degraded = [r for r in results if r.get("overlay") is False]
    if degraded:
        print(f"경고: 자막·후크 없이 만들어진 쇼츠 {len(degraded)}개 — --only <번호> --force로 다시 만든다")
        for r in degraded:
            print(f"  [{r['index']:02d}] {r['title']}")
    print(f"총 용량: {total_size:.1f}MB")
    print(f"총 길이: {total_duration:.0f}초")
    print(f"메타데이터: {metadata_path}")
    if failures:
        print(f"에러 로그: output/logs/")

    for r in results:
        print(f"  [{r['index']:02d}] {r['title']} - {r['duration']:.0f}s ({r['size_mb']:.1f}MB)")


if __name__ == "__main__":
    main()
