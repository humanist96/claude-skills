#!/usr/bin/env python3
"""1단계: 원본 영상과 대본을 준비한다. 어떤 입력이든 같은 결과 파일을 만든다.

입력(셋 중 하나)
- --video 파일 --subs 자막(.srt/.vtt): 권장. 내 영상과 내 자막
- --video 파일 --stt: 자막이 없으면 faster-whisper로 음성 인식(선택 설치: pip install faster-whisper)
- --url 주소 --i-have-rights: 내 채널·권리를 가진 YouTube 영상만. 자막(수동 우선, 없으면 자동)을 받는다.
  브라우저 쿠키는 쓰지 않는다(YT_COOKIE_BROWSER를 직접 설정한 경우만)

만드는 것(--output 폴더)
- source.json: 입력 종류, 경로·URL, 길이·해상도(로컬 영상)
- transcript.json·transcript.srt·transcript_timestamped.txt: 다음 단계(select_highlights.py, 큐레이션)가 읽는 대본

사용법
  python prepare_source.py --video 강의.mp4 --subs 강의.srt --output <W>
  python prepare_source.py --video 강의.mp4 --stt [--model small] [--lang ko] --output <W>
  python prepare_source.py --url "https://youtu.be/..." --i-have-rights --output <W>
마지막 줄: SOURCE READY type=… duration=… chunks=N
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "_vendor"))
from media import probe  # noqa: E402


def _t(s: str) -> float:
    s = s.strip().replace(",", ".")
    parts = s.split(":")
    if len(parts) == 2:
        parts = ["0", *parts]
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


def parse_subs(path: str) -> list[dict]:
    """SRT·VTT → [{"text", "timestamp": [start, end]}]. CRLF·BOM·VTT 헤더·태그·연속 중복을 정리한다."""
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    chunks, prev = [], ""
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [l for l in block.split("\n") if l.strip()]
        ti = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if ti is None:
            continue
        a, b = lines[ti].split("-->")
        b = b.strip().split(" ")[0]  # VTT 위치 설정 제거
        text = re.sub(r"<[^>]+>|\{[^}]+\}", "", " ".join(lines[ti + 1:])).strip()
        if not text or text == prev:
            continue
        chunks.append({"text": text, "timestamp": [round(_t(a), 2), round(_t(b), 2)]})
        prev = text
    return chunks


def decode_audio(path: str):
    """PyAV로 16kHz 모노 float32 배열을 만든다(영상 파일도 된다).
    faster-whisper 1.2.1의 decode_audio는 PyAV 15 이상에서 없어진 인자(metadata_errors)를 넘겨 실패하므로 직접 디코딩한다."""
    import av  # type: ignore
    import numpy as np  # type: ignore
    chunks = []
    with av.open(str(path)) as c:
        stream = c.streams.audio[0]
        rs = av.AudioResampler(format="s16", layout="mono", rate=16000)
        for frame in c.decode(stream):
            for o in rs.resample(frame):
                chunks.append(o.to_ndarray().reshape(-1))
        for o in rs.resample(None):
            chunks.append(o.to_ndarray().reshape(-1))
    return (np.concatenate(chunks).astype(np.float32) / 32768.0) if chunks else np.zeros(0, dtype=np.float32)


SMALLER = {"large-v3": ["medium", "small", "base"], "medium": ["small", "base"], "small": ["base"]}
STT_USED = [""]


def stt(video: str, model: str, lang: str) -> list[dict]:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        raise SystemExit("--stt에는 faster-whisper가 필요하다: pip install faster-whisper (처음 실행 때 모델을 내려받는다). "
                         "자막 파일(.srt·.vtt)이 있으면 --subs로 주는 편이 빠르고 정확하다")
    audio = decode_audio(video)
    tried = [model] + [m for m in SMALLER.get(model, []) if m != model]
    for i, name in enumerate(tried):
        try:
            m = WhisperModel(name, device="cpu", compute_type="int8")
            segs, _ = m.transcribe(audio, language=lang, vad_filter=True, beam_size=5)
            out = [{"text": s.text.strip(), "timestamp": [round(s.start, 2), round(s.end, 2)]} for s in segs if s.text.strip()]
            if name != model:
                print(f"WARN 음성 인식 모델을 {model} → {name}(으)로 낮췄다(메모리 부족). 화면 자막은 대본을 읽고 고쳐 쓴다")
            STT_USED[0] = name
            return out
        except (MemoryError, RuntimeError) as e:  # mkl_malloc·CUDA OOM 등. 다른 오류는 그대로 올린다
            if not re.search(r"alloc|memory", str(e), re.I) or i == len(tried) - 1:
                raise
            print(f"WARN {name} 모델 메모리 부족({str(e)[:60]}) — 더 작은 모델로 다시 시도")
    return []


def fmt(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_outputs(out: Path, chunks: list[dict], source: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "transcript.json").write_text(json.dumps({"text": " ".join(c["text"] for c in chunks), "chunks": chunks},
                                                    ensure_ascii=False, indent=2), encoding="utf-8")
    srt = []
    for i, c in enumerate(chunks, 1):
        srt += [str(i), f"{fmt(c['timestamp'][0])} --> {fmt(c['timestamp'][1])}", c["text"], ""]
    (out / "transcript.srt").write_text("\n".join(srt), encoding="utf-8")
    (out / "transcript_timestamped.txt").write_text(
        "\n".join(f"[{c['timestamp'][0]:.1f}s - {c['timestamp'][1]:.1f}s] {c['text']}" for c in chunks), encoding="utf-8")
    (out / "source.json").write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows 콘솔에서 한글 안내·오류가 깨지지 않게
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="원본 영상·대본 준비")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--video")
    src.add_argument("--url")
    ap.add_argument("--subs")
    ap.add_argument("--stt", action="store_true")
    ap.add_argument("--model", default="small")
    ap.add_argument("--lang", default="ko")
    ap.add_argument("--i-have-rights", action="store_true", help="URL 영상의 권리(내 채널·허락)를 사용자가 확인했다")
    ap.add_argument("--output", required=True)
    a = ap.parse_args(argv)
    out = Path(a.output)
    if a.video:
        if not os.path.isfile(a.video):
            raise SystemExit(f"영상 파일이 없다: {a.video}")
        info = probe(a.video)
        if not info["duration"]:
            raise SystemExit("영상 길이를 읽지 못했다. ffmpeg 설치를 확인한다: python scripts/_vendor/media.py --check")
        if a.subs:
            chunks, how = parse_subs(a.subs), "subs"
        elif a.stt:
            chunks = stt(a.video, a.model, a.lang)
            how = f"stt:{STT_USED[0] or a.model}"
        else:
            raise SystemExit("자막 파일을 --subs로 주거나, 음성 인식을 쓰려면 --stt를 붙인다")
        last = max((c["timestamp"][1] for c in chunks), default=0)
        if last > info["duration"] + 2:
            print(f"WARN 자막 끝({last:.1f}s)이 영상 길이({info['duration']:.1f}s)보다 길다 — 다른 영상의 자막인지 확인")
        source = {"type": "video", "path": str(Path(a.video).resolve()), "transcript": how, **info}
    else:
        if not a.i_have_rights:
            print("이 스킬은 권리를 가진 영상(내 채널·허락받은 영상)만 다룬다. 확인했으면 --i-have-rights를 붙인다.")
            print("SOURCE BLOCKED rights-unconfirmed")
            return 2
        import extract_subtitles as es  # noqa: E402
        srt = es.extract_subtitles(a.url, str(out), a.lang)
        if not srt:
            print("자막을 받지 못했다. 영상 파일이 있으면 --video로, 자막이 없으면 --video … --stt로 진행한다.")
            print("SOURCE FAILED subtitles")
            return 1
        chunks, how = parse_subs(srt), "youtube-subs"
        source = {"type": "url", "url": a.url, "transcript": how, "duration": max((c["timestamp"][1] for c in chunks), default=0)}
    if not chunks:
        print("SOURCE FAILED empty-transcript")
        return 1
    write_outputs(out, chunks, source)
    print(f"대본 {len(chunks)}줄 → {out / 'transcript.json'}")
    print(f"SOURCE READY type={source['type']} duration={source.get('duration', 0):.1f} chunks={len(chunks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
