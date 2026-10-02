#!/usr/bin/env python3
"""V5: 사용 범위 정책(계획서 §7.1, D8).
- 브라우저 쿠키를 자동으로 쓰지 않는다(환경변수를 직접 설정한 경우만)
- 스킬 문서·스크립트에 '봇 감지 우회', User-Agent 위장, 무작위 지연, 컨테이너 감지 쿠키 분기가 없다
- prepare_source.py는 권리 확인 없이 URL을 받지 않는다
- SKILL.md가 URL 입력 전에 권리 확인을 요구한다
양성 대조: 같은 검사기가 v1.6.1 스크립트의 우회 코드를 잡아야 한다."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shorts_fixtures import ROOT, SCRIPTS, SKILL, run_script  # noqa: E402

FORBIDDEN = {
    "우회 표현": re.compile(r"봇 감지 우회|bot[- ]detection (bypass|evasion)"),
    "User-Agent 위장": re.compile(r"--user-agent|USER_AGENTS"),
    "무작위 지연": re.compile(r"random\.uniform|random_delay"),
    "컨테이너 감지 쿠키 분기": re.compile(r"is_container_env"),
    "쿠키 파일 자동 탐색": re.compile(r"expanduser\(\"~/cookies\.txt\"\)|\"cookies\.txt\", \"output/cookies\.txt\""),
}
results: list[tuple[str, bool, str]] = []


def scan(texts: dict[str, str]) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for name, rx in FORBIDDEN.items():
        for fname, t in texts.items():
            if rx.search(t):
                hits.setdefault(name, []).append(fname)
    return hits


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    files = {p.relative_to(SKILL).as_posix(): p.read_text(encoding="utf-8", errors="replace")
             for p in SKILL.rglob("*") if p.is_file() and p.suffix in (".py", ".md", ".yaml", ".sh") and "_vendor" not in p.parts
             and "_shared" not in p.parts}
    hits = scan(files)
    results.append(("v2 스킬에 금지 패턴 없음", not hits, str(hits)))
    # 쿠키 브라우저 옵션은 환경변수를 직접 읽는 곳에서만
    for f in ("generate_shorts.py", "extract_subtitles.py"):
        t = files[f"scripts/{f}"]
        ok = all('os.environ.get("YT_COOKIE_BROWSER")' in t[max(0, m.start() - 300):m.start()] for m in re.finditer(r"--cookies-from-browser", t))
        results.append((f"{f}: --cookies-from-browser는 YT_COOKIE_BROWSER 설정 시에만", ok, ""))
    code = ("import os,sys; sys.path.insert(0, r'%s'); import generate_shorts as g, extract_subtitles as e; "
            "print(g.build_ytdlp_base_args()); print(e.build_ytdlp_base_args(use_cookies=True))") % SCRIPTS
    env = {k: v for k, v in os.environ.items() if not k.startswith("YT_")}
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, encoding="utf-8", errors="replace")
    results.append(("기본: yt-dlp 인자에 쿠키 없음", r.returncode == 0 and "cookies" not in r.stdout, r.stdout[-300:] + r.stderr[-300:]))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env={**env, "YT_COOKIE_BROWSER": "firefox"},
                       encoding="utf-8", errors="replace")
    results.append(("사용자가 설정하면 쿠키 사용", "--cookies-from-browser" in r.stdout and "firefox" in r.stdout, r.stdout[-300:]))
    r = run_script("prepare_source.py", "--url", "https://youtu.be/example", "--output", ROOT / ".workspace" / "policy_tmp")
    results.append(("권리 확인 없는 URL 거부", r.returncode == 2 and "SOURCE BLOCKED rights-unconfirmed" in r.stdout, r.stdout[-200:]))
    skill = files["SKILL.md"]
    results.append(("SKILL.md: URL 전 권리 확인", "권리 확인" in skill and "--i-have-rights" in skill and "우회" in skill, ""))
    results.append(("description: 남의 영상 가공에 쓰지 않음", "권리를 확인하지 않은 다른 사람의 영상" in skill.split("---")[1], ""))
    # 양성 대조: v1.6.1 스크립트
    old = {}
    for f in ("scripts/generate_shorts.py", "scripts/extract_subtitles.py", "reference.md", "SKILL.md"):
        g = subprocess.run(["git", "show", f"v1.6.1:skills/generate-shorts/{f}"], cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
        if g.returncode == 0:
            old[f] = g.stdout
    oh = scan(old)
    results.append(("양성 대조: v1.6.1의 우회·위장·지연 코드 검출", {"우회 표현", "User-Agent 위장", "무작위 지연", "컨테이너 감지 쿠키 분기"} <= set(oh),
                    str(sorted(oh))))
    bad = [x for x in results if not x[1]]
    for name, ok, why in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f" — {why}"))
    if bad:
        print(f"SHORTS POLICY FAILED ({len(bad)}/{len(results)})")
        return 1
    print(f"SHORTS POLICY OK — {len(results)}개 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
