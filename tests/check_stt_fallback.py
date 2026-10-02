#!/usr/bin/env python3
"""prepare_source.py --stt: 모델이 메모리 부족으로 실패하면 더 작은 모델로 다시 시도하고, 그 사실을 남긴다.
가짜 faster_whisper 모듈로 검사하므로 실제 모델·PyAV가 없어도 된다.
대조: 메모리와 무관한 오류는 삼키지 않는다. 가장 작은 모델까지 실패하면 오류를 올린다."""
from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shorts_fixtures import SCRIPTS  # noqa: E402

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "_vendor"))
import prepare_source as ps  # noqa: E402

results: list[tuple[str, bool, str]] = []


class Seg:
    def __init__(self, s, e, text):
        self.start, self.end, self.text = s, e, text


def fake(fail: dict[str, str]):
    calls: list[str] = []

    class WhisperModel:
        def __init__(self, name, **_):
            self.name = name
            calls.append(name)

        def transcribe(self, audio, **_):
            def gen():
                if self.name in fail:
                    raise RuntimeError(fail[self.name])
                yield Seg(0.0, 1.5, f" {self.name} 대본 ")
            return gen(), None
    sys.modules["faster_whisper"] = types.SimpleNamespace(WhisperModel=WhisperModel)
    return calls


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ps.decode_audio = lambda video: None  # 오디오 디코딩은 이 검사의 대상이 아니다
    calls = fake({"small": "mkl_malloc: failed to allocate memory"})
    ps.STT_USED[0] = ""
    out = ps.stt("x.mp4", "small", "ko")
    results.append(("small 메모리 부족 → base로 다시 시도", calls == ["small", "base"] and out and out[0]["text"] == "base 대본", f"{calls} {out}"))
    results.append(("source.json에 실제 쓴 모델 기록", ps.STT_USED[0] == "base", ps.STT_USED[0]))
    calls = fake({})
    ps.STT_USED[0] = ""
    out = ps.stt("x.mp4", "small", "ko")
    results.append(("정상이면 요청한 모델 그대로", calls == ["small"] and ps.STT_USED[0] == "small", str(calls)))
    calls = fake({"small": "Unsupported model format"})
    try:
        ps.stt("x.mp4", "small", "ko")
        results.append(("대조: 메모리와 무관한 오류는 올린다", False, f"삼켜짐 {calls}"))
    except RuntimeError:
        results.append(("대조: 메모리와 무관한 오류는 올린다", calls == ["small"], str(calls)))
    calls = fake({"small": "failed to allocate memory", "base": "failed to allocate memory"})
    try:
        ps.stt("x.mp4", "small", "ko")
        results.append(("대조: 가장 작은 모델까지 실패하면 오류", False, f"삼켜짐 {calls}"))
    except RuntimeError:
        results.append(("대조: 가장 작은 모델까지 실패하면 오류", calls == ["small", "base"], str(calls)))
    bad = [x for x in results if not x[1]]
    for name, ok, why in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f" — {why}"))
    if bad:
        print(f"STT FALLBACK FAILED ({len(bad)}/{len(results)})")
        return 1
    print(f"STT FALLBACK OK — {len(results)}개 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
