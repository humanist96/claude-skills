#!/usr/bin/env python3
"""R1: 리서치 공유 엔진(prepare_sources·numparse·source-tiers)이 shared/optional 한 곳에만 있고,
두 스킬(data-collector, content-research)의 _vendor 사본이 원본과 같으며, data-collector 검증이 공유 엔진으로 통과하는지 확인한다.
오버라이드 폴더의 references/source-tiers.yaml을 자동으로 쓰는지도 확인한다.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ["prepare_sources.py", "numparse.py", "source-tiers.yaml"]
SKILLS = {"data-collector": ROOT / "plugins/kevin-skills-book/skills/data-collector",
          "content-research": ROOT / "plugins/kevin-skills-creator/skills/content-research"}
COLLECTOR_TESTS = [("check_collector_practice.py", "COLLECTOR PRACTICE OK"), ("check_prepare_sources.py", "PREPARE SOURCES OK"),
                   ("check_trend_stats.py", "TREND STATS OK"), ("check_report_verify.py", "REPORT VERIFY CONTROL OK")]
results: list[tuple[str, bool, str]] = []


def norm(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    for f in ENGINE:
        src = ROOT / "shared/optional" / f
        results.append((f"원본 shared/optional/{f}", src.is_file(), ""))
        for name, d in SKILLS.items():
            cp = d / "scripts/_vendor" / f
            results.append((f"{name} _vendor/{f} = 원본", cp.is_file() and norm(cp.read_bytes()) == norm(src.read_bytes()), str(cp)))
            stray = [p for p in d.rglob(f) if "_vendor" not in p.parts]
            results.append((f"{name}에 {f} 별도 사본 없음", not stray, str(stray)))
    for name, d in SKILLS.items():
        users = [p for p in (d / "scripts").glob("*.py") if re.search(r"from (numparse|prepare_sources) import", p.read_text(encoding="utf-8"))]
        bad = [p.name for p in users if '"_vendor"' not in p.read_text(encoding="utf-8")]
        results.append((f"{name} 스크립트가 _vendor 엔진을 씀", bool(users) and not bad, f"사용 {[p.name for p in users]}, 경로 없음 {bad}"))
    for t, token in COLLECTOR_TESTS:
        r = subprocess.run([sys.executable, str(ROOT / "tests" / t)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        results.append((f"data-collector {t}", token in r.stdout, r.stdout[-200:]))
    # 숫자 추출 회귀(평가 중 발견): 영어 단어 뒤 숫자, 띄어 쓴 영어 단어, 영어·한글 퍼센트
    sys.path.insert(0, str(ROOT / "shared/optional"))
    from numparse import extract, trivial  # noqa: E402
    cases = [("only using 20% of Astra", [("percent", 20.0)]), ("price is 20%.", [("percent", 20.0)]),
             ("up 30 percent", [("percent", 30.0)]), ("20 퍼센트 늘었다", [("percent", 20.0)]),
             ("1조 2,000억 원", [("money", 1.2e12)]), ("$13.6B 매출", [("money", 13.6e9)]), ("GPT-4o 출시", [])]
    for text, want in cases:
        got = [(n.kind, n.value) for n in extract(text)]
        results.append((f"숫자 추출 '{text}'", got == want, str(got)))
    yr = extract("2026 AI 결산")
    results.append(("'2026 AI'는 연도(단위 없음)", len(yr) == 1 and trivial(yr[0]), str([(n.text, n.unit) for n in yr])))
    # 오버라이드 신뢰 등급 자동 적용(프로젝트 폴더)
    eng = SKILLS["content-research"] / "scripts/_vendor/prepare_sources.py"
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        T = Path(td)
        (T / "in.json").write_text(json.dumps([{"title": "사내 리서치", "url": "https://our-lab.example/r/1", "date": "2026-10-01", "text": "x"}]),
                                   encoding="utf-8")
        run = lambda: subprocess.run([sys.executable, str(eng), str(T / "in.json"), "--out", str(T / "o.json"), "--today", "2026-10-02"],  # noqa: E731
                                     cwd=T, capture_output=True, text=True, encoding="utf-8", errors="replace")
        run()
        before = json.loads((T / "o.json").read_text(encoding="utf-8"))["sources"][0]["tier"]
        ov = T / ".claude/claude-skills/content-research/references"
        ov.mkdir(parents=True)
        (ov / "source-tiers.yaml").write_text("tiers:\n  A:\n    label: 사내 인정\n    kinds: []\n    domains: [our-lab.example]\n", encoding="utf-8")
        run()
        after = json.loads((T / "o.json").read_text(encoding="utf-8"))["sources"][0]["tier"]
        results.append(("오버라이드 신뢰 등급 자동 적용(U → A)", before == "U" and after == "A", f"{before} → {after}"))
    bad = [x for x in results if not x[1]]
    for name, ok, why in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f" — {why}"))
    if bad:
        print(f"SHARED ENGINE FAILED ({len(bad)}/{len(results)})")
        return 1
    print(f"SHARED ENGINE OK — {len(results)}개 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
