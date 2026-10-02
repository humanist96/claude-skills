#!/usr/bin/env python3
"""V1: 실습 강의 영상·자막·정답표가 서로 맞고, 제3자 방송 자막 샘플이 실습 자료에서 빠졌는지 확인한다."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shorts_fixtures import KEY, PRACTICE, ROOT, SRT, TIMINGS, VIDEO  # noqa: E402

results: list[tuple[str, bool, str]] = []


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    r = subprocess.run([sys.executable, str(ROOT / "tools/dev/make_shorts_practice.py"), "--check"], capture_output=True, text=True, encoding="utf-8")
    results.append(("자막·정답표 재현 가능(낭독 시간 기록에서 다시 계산)", "REPRODUCIBLE" in r.stdout, r.stdout[-200:] + r.stderr[-200:]))
    results.append(("영상 파일 있음(1MB 이하)", VIDEO.is_file() and VIDEO.stat().st_size < 1_000_000, str(VIDEO.stat().st_size if VIDEO.is_file() else 0)))
    try:
        from media import ffmpeg_path, probe  # noqa: E402
        have_ff = bool(ffmpeg_path())
    except Exception:  # noqa: BLE001
        have_ff = False
    if have_ff:
        info = probe(str(VIDEO))
        results.append(("영상 길이·해상도·오디오가 정답표와 같음", abs(info["duration"] - KEY["duration"]) < 0.5 and
                        (info["width"], info["height"]) == (KEY["width"], KEY["height"]) and info["has_audio"], str(info)))
    else:
        print("SKIP 영상 정보 확인(ffmpeg 없음)")
    srt = SRT.read_text(encoding="utf-8")
    ends = [t for t in re.findall(r"--> (\d\d:\d\d:\d\d,\d{3})", srt)]
    last = sum(float(x) * m for x, m in zip(ends[-1].replace(",", ".").split(":"), (3600, 60, 1))) if ends else 0
    results.append(("자막 줄 수 = 낭독 문장 수", len(ends) == len(TIMINGS), f"{len(ends)} vs {len(TIMINGS)}"))
    results.append(("자막 끝이 영상 길이 안", 0 < last <= KEY["duration"], f"{last} / {KEY['duration']}"))
    segs = KEY["segments"]
    ordered = all(a["end"] <= b["start"] for a, b in zip(segs, segs[1:]))
    results.append(("구간 순서·겹침 없음", ordered, ""))
    usable = [s for s in segs if s["usable"]]
    results.append(("쓸 만한 구간 3개, 모두 15~60초", len(usable) == 3 and all(15 <= s["end"] - s["start"] <= 60 for s in usable),
                    str([(s["id"], round(s["end"] - s["start"], 1)) for s in usable])))
    results.append(("쓰면 안 되는 구간(인사·잡담·마무리)", KEY["not_usable"] == ["intro", "aside", "outro"], str(KEY["not_usable"])))
    xl = " ".join(l["text"] for l in TIMINGS if l["segment"] == "xlookup")
    results.append(("숫자 사실(주당 2시간·30분)이 낭독에 있음", "2시간" in xl and "30분" in xl, ""))
    results.append(("제3자 방송 자막 샘플(output/) 제거", not (PRACTICE / "output").exists(), ""))
    cat = json.loads((PRACTICE.parent / "catalog.json").read_text(encoding="utf-8"))
    sets = {s["id"]: s for s in cat["sets"]}
    results.append(("catalog: shorts-offline 삭제", "shorts-offline" not in sets, ""))
    for sid in ("shorts-lecture", "shorts-answer-key"):
        s = sets.get(sid)
        results.append((f"catalog {sid}", bool(s) and all(list(PRACTICE.parent.glob(f)) for f in s["files"]), str(s)[:160]))
    bad = [x for x in results if not x[1]]
    for name, ok, why in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f" — {why}"))
    if bad:
        print(f"SHORTS PRACTICE FAILED ({len(bad)}/{len(results)})")
        return 1
    print(f"SHORTS PRACTICE OK — {len(results)}개 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
