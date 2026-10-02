#!/usr/bin/env python3
"""generate-shorts 실습 강의 영상(자체 제작)·자막·정답표를 만든다.

왜
- v1.6.1 실습 자료(오프라인 데모)는 제3자 방송 영상의 자동자막이라 배포 권리가 없다(handoff H3).
- 쇼츠 품질의 핵심은 '독립적으로 이해되는 구간 고르기'다. 채점하려면 좋은 구간과 쓰면 안 되는 구간이 분명한 영상이 필요하다.

만드는 것(samples/generate-shorts/)
- inputs/엑셀팁_강의.mp4: 슬라이드 6장 + 한국어 낭독(edge-tts), 960x540, 약 2분 30초
- inputs/엑셀팁_강의.srt: 문장 단위 자막(낭독 길이로 계산한 정확한 시간)
- inputs/lecture_timings.json: 문장별 시간(영상 생성의 원본 기록)
- answer_key.json: 구간 정답(쇼츠로 쓸 구간 3개, 쓰면 안 되는 구간 3개, 숫자·사실)

영상·음성은 edge-tts(인터넷 필요)로 한 번 만들어 커밋한다. --check는 lecture_timings.json에서 자막·정답표를 다시 계산해 파일과 같은지 본다.
사용법: python tools/dev/make_shorts_practice.py [--build] [--check]
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "plugins/kevin-skills-practice/skills/practice-samples/samples/generate-shorts"
VIDEO = "엑셀팁_강의.mp4"
SRT = "엑셀팁_강의.srt"
VOICE = "ko-KR-SunHiNeural"
GAP = 0.35  # 문장 사이 쉼(초)
W, H = 960, 540

SEGMENTS = [
    {"id": "intro", "slide": ("엑셀 업무 시간 줄이기", ["오늘의 꿀팁 3가지"]), "usable": False,
     "why": "인사·구독 요청뿐, 정보 없음",
     "lines": ["안녕하세요, 엑셀 한 스푼입니다.", "오늘은 엑셀 업무 시간을 줄이는 방법 세 가지를 이야기해 보겠습니다.",
               "시작하기 전에 구독과 좋아요 부탁드려요."]},
    {"id": "xlookup", "slide": ("팁 1. VLOOKUP 대신 XLOOKUP", ["찾는 값이 어느 열에 있어도 OK", "열을 끼워 넣어도 수식이 안 깨짐"]),
     "usable": True, "why": "팁 하나가 처음부터 결론(주당 2시간 → 30분)까지 완결",
     "lines": ["첫 번째, VLOOKUP 대신 XLOOKUP을 쓰세요.",
               "VLOOKUP은 찾는 값이 표의 맨 왼쪽에 있어야 하지만, XLOOKUP은 어느 열에 있든 찾을 수 있습니다.",
               "중간에 열을 하나 끼워 넣어도 수식이 깨지지 않아요.",
               "저희 팀은 이것만 바꿨는데, 월말 보고서를 고치는 시간이 주당 2시간에서 30분으로 줄었습니다."]},
    {"id": "table", "slide": ("팁 2. 범위를 '표'로 만들기", ["Ctrl + T", "새 행에 수식·서식 자동 적용", "피벗도 새 데이터 자동 포함"]),
     "usable": True, "why": "Ctrl+T 하나로 끝나는 독립 팁, 마지막 문장이 공감 포인트",
     "lines": ["두 번째, 데이터 범위를 표로 만드세요.", "범위를 선택하고 컨트롤 T를 누르면 됩니다.",
               "표로 만들면 새 행을 추가할 때 수식과 서식이 자동으로 따라오고, 피벗 테이블도 새 데이터를 자동으로 포함합니다.",
               "이걸 모르고 매달 범위를 다시 잡는 분이 정말 많습니다."]},
    {"id": "aside", "slide": ("잠깐 쉬어 가기", ["점심 이야기"]), "usable": False, "why": "주제와 무관한 잡담",
     "lines": ["잠깐 다른 얘기를 하자면, 어제 점심에 먹은 김치찌개가 정말 맛있었는데요.", "회사 앞에 새로 생긴 집입니다.",
               "아무튼 다시 엑셀 이야기로 돌아가겠습니다."]},
    {"id": "flashfill", "slide": ("팁 3. 빠른 채우기", ["Ctrl + E", "첫 칸만 직접 입력", "결과는 꼭 한 번 확인"]),
     "usable": True, "why": "문제 상황 → 해결 → 주의점까지 한 구간에 있음",
     "lines": ["세 번째, 빠른 채우기입니다.", "이름과 전화번호가 한 칸에 섞여 있을 때, 옆 칸에 첫 번째 결과만 직접 입력하고 컨트롤 E를 누르면 나머지를 엑셀이 알아서 채웁니다.",
               "함수를 몰라도 됩니다.", "단, 패턴이 일정하지 않으면 틀리게 채우니까 결과는 꼭 한 번 훑어보세요."]},
    {"id": "outro", "slide": ("정리", ["XLOOKUP · 표(Ctrl+T) · 빠른 채우기(Ctrl+E)", "다음 영상: 피벗 테이블"]), "usable": False,
     "why": "앞 내용 요약과 다음 영상 예고",
     "lines": ["오늘 세 가지만 기억하셔도 엑셀 작업이 훨씬 빨라집니다.", "다음 영상에서는 피벗 테이블을 다뤄 보겠습니다."]},
]


# ---------- 계산(타이밍 → 자막·정답표) ----------

def fmt(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt_from(timings: list[dict]) -> str:
    out = []
    for i, t in enumerate(timings, 1):
        out += [str(i), f"{fmt(t['start'])} --> {fmt(t['end'])}", t["text"], ""]
    return "\n".join(out)


def key_from(timings: list[dict], total: float) -> dict:
    segs = []
    for seg in SEGMENTS:
        rows = [t for t in timings if t["segment"] == seg["id"]]
        segs.append({"id": seg["id"], "start": rows[0]["start"], "end": rows[-1]["end"], "usable": seg["usable"], "why": seg["why"],
                     "first_line": rows[0]["text"]})
    return {
        "video": VIDEO, "srt": SRT, "duration": round(total, 2), "width": W, "height": H,
        "segments": segs,
        "usable": [s["id"] for s in segs if s["usable"]],
        "not_usable": [s["id"] for s in segs if not s["usable"]],
        "facts": {"xlookup": ["주당 2시간", "30분"], "table": ["Ctrl+T(컨트롤 T)"], "flashfill": ["Ctrl+E(컨트롤 E)"]},
        "must_not": ["구독·좋아요 요청을 쇼츠 후크로 쓰기", "김치찌개 잡담 구간 사용", "자료에 없는 수치(예: '10배 빨라진다')"],
        "note": "구간 시간은 낭독 길이로 계산한 정확한 값이다. 쇼츠는 15~60초이므로 각 usable 구간을 그대로 쓰거나 문장 경계에서 줄인다.",
    }


# ---------- 생성(edge-tts + Pillow + ffmpeg) ----------

def _ffmpeg() -> str:
    sys.path.insert(0, str(ROOT / "shared/optional"))
    from media import require_ffmpeg  # noqa: E402
    return require_ffmpeg()


def _probe_dur(ff: str, path: Path) -> float:
    sys.path.insert(0, str(ROOT / "shared/optional"))
    from media import probe  # noqa: E402
    return probe(str(path))["duration"]


async def _tts(text: str, path: Path) -> None:
    import edge_tts  # type: ignore
    await edge_tts.Communicate(text, VOICE, rate="+5%").save(str(path))


def slide_png(title: str, bullets: list[str], path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore
    sys.path.insert(0, str(ROOT / "shared/scripts"))
    from fonts import find_font  # noqa: E402
    font = find_font("bold") or find_font()
    img = Image.new("RGB", (W, H), (23, 37, 64))
    d = ImageDraw.Draw(img)
    tf, bf = ImageFont.truetype(font, 46), ImageFont.truetype(font, 32)
    d.rectangle([0, 0, W, 8], fill=(255, 196, 0))
    d.text((60, 70), title, font=tf, fill=(255, 255, 255))
    y = 190
    for b in bullets:
        d.text((80, y), "• " + b, font=bf, fill=(220, 230, 245))
        y += 70
    d.text((60, H - 50), "엑셀 한 스푼 · 실습용 자체 제작 영상", font=ImageFont.truetype(font, 20), fill=(140, 160, 190))
    img.save(path)


def build() -> None:
    ff = _ffmpeg()
    inp = OUT / "inputs"
    inp.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        T = Path(td)
        timings, t, audio_list, slide_list = [], 0.0, [], []
        silence = T / "gap.wav"
        subprocess.run([ff, "-y", "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono", "-t", str(GAP), str(silence)], check=True, capture_output=True)
        n = 0
        for si, seg in enumerate(SEGMENTS):
            png = T / f"slide{si}.png"
            slide_png(*seg["slide"], png)
            seg_start = t
            for line in seg["lines"]:
                n += 1
                mp3 = T / f"l{n}.mp3"
                asyncio.run(_tts(line, mp3))
                wav = T / f"l{n}.wav"
                subprocess.run([ff, "-y", "-i", str(mp3), "-ar", "24000", "-ac", "1", str(wav)], check=True, capture_output=True)
                dur = _probe_dur(ff, wav)
                timings.append({"segment": seg["id"], "text": line, "start": round(t, 3), "end": round(t + dur, 3)})
                audio_list += [wav, silence]
                t += dur + GAP
            slide_list.append((png, t - seg_start))
        (T / "a.txt").write_text("".join(f"file '{p.as_posix()}'\n" for p in audio_list), encoding="utf-8")
        (T / "v.txt").write_text("".join(f"file '{p.as_posix()}'\nduration {d:.3f}\n" for p, d in slide_list)
                                 + f"file '{slide_list[-1][0].as_posix()}'\n", encoding="utf-8")
        subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(T / "v.txt"), "-f", "concat", "-safe", "0", "-i", str(T / "a.txt"),
                        "-vf", f"fps=5,format=yuv420p", "-c:v", "libx264", "-tune", "stillimage", "-crf", "32", "-preset", "veryslow",
                        "-c:a", "aac", "-b:a", "32k", "-ac", "1", "-shortest", "-movflags", "+faststart", str(inp / VIDEO)],
                       check=True, capture_output=True)
        total = _probe_dur(ff, inp / VIDEO)
    (inp / "lecture_timings.json").write_text(json.dumps({"voice": VOICE, "gap": GAP, "duration": round(total, 2), "lines": timings},
                                                         ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    write_text_artifacts(OUT)
    print(f"built {inp / VIDEO} ({(inp / VIDEO).stat().st_size // 1024}KB, {total:.1f}s)")


def write_text_artifacts(out: Path) -> None:
    tj = json.loads((OUT / "inputs/lecture_timings.json").read_text(encoding="utf-8"))
    (out / "inputs").mkdir(parents=True, exist_ok=True)
    (out / "inputs" / SRT).write_text(srt_from(tj["lines"]), encoding="utf-8", newline="\n")
    (out / "answer_key.json").write_text(json.dumps(key_from(tj["lines"], tj["duration"]), ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    if "--build" in argv:
        build()
        return 0
    if "--check" in argv:
        def norm(b: bytes) -> bytes:
            return b.replace(b"\r\n", b"\n")
        with tempfile.TemporaryDirectory() as td:
            write_text_artifacts(Path(td))
            pairs = [(OUT / "inputs" / SRT, Path(td) / "inputs" / SRT), (OUT / "answer_key.json", Path(td) / "answer_key.json")]
            diff = [a.name for a, b in pairs if not a.is_file() or norm(a.read_bytes()) != norm(b.read_bytes())]
        print("DIFF: " + ", ".join(diff) if diff else "REPRODUCIBLE")
        return 1 if diff else 0
    write_text_artifacts(OUT)
    print("written: srt, answer_key.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
