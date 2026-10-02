"""content-research 테스트 공용: 경로, 스크립트 실행, 실습 피드 정리 결과."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/kevin-skills-creator/skills/content-research"
SCRIPTS = SKILL / "scripts"
PRACTICE = ROOT / "plugins/kevin-skills-practice/skills/practice-samples/samples/content-research"
FEED = PRACTICE / "inputs" / "주간_테크뉴스.xml"
KEY = json.loads((PRACTICE / "answer_key.json").read_text(encoding="utf-8"))
GOOD = ROOT / "tests/fixtures/research_good_plan_youtube.md"


def run_script(name: str, *args, cwd=None) -> subprocess.CompletedProcess:
    path = SCRIPTS / name if (SCRIPTS / name).is_file() else SCRIPTS / "_vendor" / name
    return subprocess.run([sys.executable, str(path), *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=cwd)


def prepared(tmp: Path) -> Path:
    out = tmp / "sources.json"
    w = KEY["window"]
    r = run_script("prepare_sources.py", FEED, "--out", out, "--today", KEY["as_of"], "--since", w["since"], "--until", w["until"])
    if "SOURCES READY" not in r.stdout:
        raise RuntimeError(r.stdout[-500:] + r.stderr[-500:])
    return out


def json_head(stdout: str, marker: str):
    return json.loads(stdout[: stdout.rindex(marker)])
