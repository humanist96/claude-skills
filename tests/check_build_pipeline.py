#!/usr/bin/env python3
"""D5: build_pipeline.py가 만든 패키지가 검사·시험 실행을 통과하고, 변조한 패키지는 검사에 걸리는지 확인한다.
도메인 프로필(한국어 뉴스 피드, 고정 연도 없음, 키워드 판별)과 v1.6.1 워크플로의 결함(커밋 권한 없음)도 확인한다.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _collector_fixtures import ROOT, SCRIPTS, SKILL, run_script  # noqa: E402

sys.path.insert(0, str(SCRIPTS))
from build_pipeline import REQUIRED, kst_to_cron  # noqa: E402
from profiles import detect, load_profiles  # noqa: E402

results: list[tuple[str, bool, str]] = []


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    for hhmm, cron in (("09:00", "0 0 * * *"), ("07:30", "30 22 * * *"), ("18:05", "5 9 * * *")):
        results.append((f"한국 {hhmm} → cron {cron}", kst_to_cron(hhmm)[0] == cron, kst_to_cron(hhmm)[0]))
    profs = load_profiles(project_dir=tempfile.gettempdir(), home=tempfile.gettempdir())
    results.append(("기본 프로필 6종", sorted(profs) == ["beauty", "finance", "food", "game", "realestate", "tech"], str(sorted(profs))))
    for name, p in profs.items():
        free = p["sources"]["free"]
        ko = any("news.google.com" in s.get("url", "") and "hl=ko" in s.get("url", "") for s in free)
        years = [s["query_template"] for s in free if re.search(r"20\d\d", s.get("query_template", ""))]
        results.append((f"{name}: 한국어 뉴스 피드·고정 연도 없음", ko and not years, f"ko={ko} years={years}"))
    for kw, dom in (("제로슈거 음료", "food"), ("HBM 반도체", "finance"), ("AI 에이전트", "tech"), ("강남 아파트 전세", "realestate"),
                    ("물류 로봇", "general")):
        results.append((f"'{kw}' → {dom}", detect(kw, profs)[0] == dom, detect(kw, profs)[0]))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        T = Path(td)
        pkg = T / "data_pipeline"
        r = run_script("build_pipeline.py", "--keyword", "제로슈거 음료", "--out", pkg, "--time", "07:30", "--zip")
        results.append(("생성·검사·시험 실행 통과", "PIPELINE READY files=10 selftest=ok" in r.stdout, r.stdout[-400:] + r.stderr[-300:]))
        results.append(("필수 파일 10개", all((pkg / f).is_file() for f in REQUIRED) and len(REQUIRED) == 10, ""))
        results.append(("zip 생성", (T / "data_pipeline.zip").is_file(), ""))
        wf = (pkg / ".github/workflows/daily_collect.yml").read_text(encoding="utf-8")
        results.append(("cron 30 22 * * *", "cron: '30 22 * * *'" in wf, wf[:200]))
        results.append(("시험 실행 흔적 정리", not (pkg / "reports").exists() and not (pkg / "data").exists(), ""))
        r = run_script("build_pipeline.py", "--keyword", "x", "--out", pkg)
        results.append(("비어 있지 않은 폴더 덮어쓰기 거부", r.returncode != 0, r.stdout[-200:] + r.stderr[-200:]))
        # 평가에서 나온 개선: 1일 기간 시험 실행, Slack 새 기사 목록, 구글 뉴스 기간 제한
        r = run_script("build_pipeline.py", "--keyword", "제로슈거 음료", "--out", T / "daily", "--window-days", "1")
        results.append(("수집 기간 1일로 만들어도 시험 실행 통과", "PIPELINE READY" in r.stdout, r.stdout[-300:]))
        sys.path.insert(0, str(pkg))
        import collector  # type: ignore  # noqa: E402
        import slack_notifier  # type: ignore  # noqa: E402
        gurls = [f["url"] for f in collector.feeds_from_config({"keywords": ["제로슈거 음료"], "window_days": 7})]
        results.append(("구글 뉴스 검색에 기간 제한(when:7d)", any("when%3A7d" in u and "hl=ko" in u for u in gurls), str(gurls)))
        from datetime import date as _d
        items = [{"title": "오늘 기사", "url": "https://example.com/a", "publisher": "예시신문", "published": "2026-10-02"},
                 {"title": "사흘 전 기사", "url": "https://example.com/b", "publisher": "예시일보", "published": "2026-09-29"}]
        msg = slack_notifier.format_message(items, {"count": 2, "top_terms": [{"term": "가격", "articles": 2}]},
                                            {"keywords": ["제로슈거 음료"], "slack": {"new_days": 1}}, "reports/x.md", _d(2026, 10, 2))
        results.append(("Slack 메시지에 새 기사 제목·링크, 오래된 기사 제외", "<https://example.com/a|오늘 기사>" in msg and "사흘 전" not in msg
                        and "새 기사 1건" in msg, msg))
        env = {**__import__("os").environ, "SLACK_DRY_RUN": "1", "PYTHONIOENCODING": "utf-8"}
        rr = subprocess.run([sys.executable, "run_pipeline.py", "--offline-feed", "samples/sample_feed.xml"], cwd=pkg, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", env=env)
        results.append(("SLACK_DRY_RUN=1이면 보내지 않고 메시지 출력", "dry-run" in rr.stdout and "예시 기사" in rr.stdout and "PIPELINE RUN OK" in rr.stdout,
                        rr.stdout[-400:] + rr.stderr[-300:]))
        for d in ("reports", "data", "__pycache__"):
            shutil.rmtree(pkg / d, ignore_errors=True)

        def tampered(name: str, edit, expect: str, selftest: bool = False):
            d = T / f"t_{len(results)}"
            shutil.copytree(pkg, d)
            edit(d)
            args = ["--check", d] + ([] if selftest else ["--no-selftest"])
            rr = run_script("build_pipeline.py", *args)
            results.append((name, "PIPELINE FAILED" in rr.stdout and expect in rr.stdout, rr.stdout[-300:]))

        def rep(rel, old, new):
            def f(d):
                p = d / rel
                t = p.read_text(encoding="utf-8")
                assert old in t, (rel, old)
                p.write_text(t.replace(old, new), encoding="utf-8")
            return f
        tampered("워크플로 없음", lambda d: (d / ".github/workflows/daily_collect.yml").unlink(), "필수 파일 없음")
        tampered("config에 웹훅 주소", rep("config.yaml", 'webhook_url: ""', 'webhook_url: "https://hooks.slack.com/services/T000/B000/XXXX"'), "webhook_url")
        tampered("수동 실행 없음", rep(".github/workflows/daily_collect.yml", "  workflow_dispatch:", "  push:"), "workflow_dispatch")
        tampered("cron 없음", rep(".github/workflows/daily_collect.yml", "    - cron: '30 22 * * *'", "    - cron: ''"), "cron")
        tampered("Secrets 미사용", rep(".github/workflows/daily_collect.yml", "${{ secrets.SLACK_WEBHOOK_URL }}", '""'), "Secrets")
        tampered("환경변수 우선 아님", rep("slack_notifier.py", 'os.environ.get("SLACK_WEBHOOK_URL") or ', ""), "환경변수")
        tampered("문법 오류", rep("analyzer.py", "def analyze(", "def analyze(("), "문법 오류")
        tampered("YAML 오류", rep("config.yaml", "keywords:", "keywords: [\n"), "YAML")
        tampered("중복 제거가 깨지면 시험 실행 실패", rep("collector.py", "        if key in seen:\n            continue\n", ""), "3건이어야", selftest=True)
        # v1.6.1 워크플로 템플릿: 보고서를 커밋하는데 contents: write 권한이 없다
        old = subprocess.run(["git", "show", "v1.6.1:skills/data-collector/templates/github_actions_template.yml"], cwd=ROOT,
                             capture_output=True, encoding="utf-8", errors="replace")
        if old.returncode == 0:
            tampered("v1.6.1 워크플로: 커밋 권한 없음 검출",
                     lambda d: (d / ".github/workflows/daily_collect.yml").write_text(old.stdout.replace("{{KEYWORD}}", "x"), encoding="utf-8"),
                     "contents: write")
        else:
            results.append(("v1.6.1 워크플로: 커밋 권한 없음 검출", False, "git show 실패(태그 없음)"))
    results.append(("스킬 폴더에 시험 실행 흔적 없음", not (SKILL / "templates/pipeline/reports").exists(), ""))
    bad = [x for x in results if not x[1]]
    for name, ok, why in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f" — {why}"))
    if bad:
        print(f"PIPELINE CHECK FAILED ({len(bad)}/{len(results)})")
        return 1
    print(f"PIPELINE OK — {len(results)}개 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
