"""generate-shorts 테스트 공용: 경로, 스크립트 실행, 실습 강의 영상·정답표, 정상 하이라이트."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/kevin-skills-creator/skills/generate-shorts"
SCRIPTS = SKILL / "scripts"
PRACTICE = ROOT / "plugins/kevin-skills-practice/skills/practice-samples/samples/generate-shorts"
VIDEO = PRACTICE / "inputs" / "엑셀팁_강의.mp4"
SRT = PRACTICE / "inputs" / "엑셀팁_강의.srt"
KEY = json.loads((PRACTICE / "answer_key.json").read_text(encoding="utf-8"))
TIMINGS = json.loads((PRACTICE / "inputs" / "lecture_timings.json").read_text(encoding="utf-8"))["lines"]
sys.path.insert(0, str(SCRIPTS / "_vendor"))


def run_script(name: str, *args, cwd=None, env=None, timeout=600) -> subprocess.CompletedProcess:
    path = SCRIPTS / name if (SCRIPTS / name).is_file() else SCRIPTS / "_vendor" / name
    return subprocess.run([sys.executable, str(path), *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=cwd, env=env, timeout=timeout)


def good_highlights(ids=("xlookup", "table", "flashfill")) -> list[dict]:
    """정답표의 쓸 만한 구간으로 만든 정상 highlights.json(자막은 낭독 시간 그대로)."""
    out = []
    titles = {"xlookup": ("VLOOKUP 말고 XLOOKUP", "열 위치 상관없이 찾기"), "table": ("범위를 표로 바꾸는 단축키", "Ctrl+T 하나면 끝"),
              "flashfill": ("함수 없이 데이터 나누기", "Ctrl+E 빠른 채우기")}
    for i, sid in enumerate(ids, 1):
        seg = next(s for s in KEY["segments"] if s["id"] == sid)
        subs = [{"start": round(l["start"] - seg["start"], 2), "end": round(l["end"] - seg["start"], 2), "text": l["text"]}
                for l in TIMINGS if l["segment"] == sid]
        out.append({"index": i, "start": seg["start"], "end": seg["end"], "title": titles[sid][0], "hook": titles[sid][1],
                    "reason": seg["why"], "subtitles": subs})
    return out
