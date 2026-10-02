"""data-collector 테스트 공용: 경로, 스크립트 실행, 실습 기사 묶음 정리 결과."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/kevin-skills-book/skills/data-collector"
SCRIPTS = SKILL / "scripts"
PRACTICE = ROOT / "plugins/kevin-skills-practice/skills/practice-samples/samples/data-collector"
ARTICLES = PRACTICE / "inputs" / "제로음료_기사묶음"
KEY = json.loads((PRACTICE / "answer_key.json").read_text(encoding="utf-8"))
EXAMPLE = ROOT / "tests" / "fixtures" / "collector_good_report.md"  # 실습 기사 묶음 기준 보고서(평가 누설을 막으려고 스킬 예시와 분리)
SKILL_EXAMPLES = SKILL / "examples"


def run_script(name: str, *args, cwd=None) -> subprocess.CompletedProcess:
    path = SCRIPTS / name if (SCRIPTS / name).is_file() else SCRIPTS / "_vendor" / name  # 공유 엔진은 _vendor
    return subprocess.run([sys.executable, str(path), *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=cwd)


def prepared(tmp: Path) -> Path:
    """실습 기사 묶음을 정답표의 기간으로 정리한 sources.json 경로."""
    out = tmp / "sources.json"
    w = KEY["window"]
    r = run_script("prepare_sources.py", ARTICLES, "--out", out, "--today", KEY["as_of"], "--since", w["since"], "--until", w["until"])
    if "SOURCES READY" not in r.stdout:
        raise RuntimeError(r.stdout[-500:] + r.stderr[-500:])
    return out


def by_orig(sources: dict) -> dict:
    return {s["orig"]: s for s in sources["sources"]}


def json_head(stdout: str, marker: str):
    return json.loads(stdout[: stdout.rindex(marker)])
