#!/usr/bin/env python3
"""자동화 패키지(모드 2)를 만든다: templates/pipeline을 복사하고 config.yaml·워크플로를 채운 뒤 검사·시험 실행한다.

만드는 것: run_pipeline.py, collector.py, analyzer.py, report_generator.py, slack_notifier.py, config.yaml,
requirements.txt, README.md, .github/workflows/daily_collect.yml, samples/sample_feed.xml

검사(하나라도 실패하면 PIPELINE FAILED)
- 필수 파일, config.yaml·워크플로 YAML 문법
- 워크플로: schedule cron, workflow_dispatch, Secrets로 웹훅 전달, contents: write 권한, run_pipeline.py 실행
- config.yaml의 slack.webhook_url이 비어 있음, 어떤 파일에도 실제 웹훅 주소가 없음
- slack_notifier.py가 환경변수를 먼저 읽음, 모든 .py 문법
- 시험 실행: 예시 피드로 네트워크 없이 돌려 다이제스트가 생기고 중복·기간 밖 기사가 빠지는지

사용법
  python build_pipeline.py --keyword "공유 전기자전거" [--keyword 킥보드] [--domain food] --out <W>/data_pipeline
                           [--time 09:00] [--window-days 7] [--zip] [--no-selftest] [--force]
  python build_pipeline.py --check <패키지 폴더>
마지막 줄: PIPELINE READY files=N selftest=ok|skipped 또는 PIPELINE FAILED
"""
from __future__ import annotations

import argparse
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "templates" / "pipeline"
sys.path.insert(0, str(HERE))

REQUIRED = ["run_pipeline.py", "collector.py", "analyzer.py", "report_generator.py", "slack_notifier.py", "config.yaml",
            "requirements.txt", "README.md", ".github/workflows/daily_collect.yml", "samples/sample_feed.xml"]
WEBHOOK = re.compile(r"hooks\.slack\.com/services/[A-Za-z0-9/]+")


def _yaml():
    try:
        import yaml  # type: ignore
        return yaml
    except ImportError:
        sys.exit("pyyaml이 필요하다: pip install pyyaml")


def kst_to_cron(hhmm: str) -> tuple[str, str]:
    h, m = (int(x) for x in hhmm.split(":"))
    uh = (h - 9) % 24
    return f"{m} {uh} * * *", f"매일 한국 시각 {h:02d}:{m:02d}(UTC {uh:02d}:{m:02d})"


def render_config(keywords: list[str], feeds: list[dict], window_days: int, domain: str) -> str:
    lines = ["# 뉴스 다이제스트 설정. 값을 바꾼 뒤 python run_pipeline.py --no-notify 로 확인한다.",
             f"# 도메인 프로필: {domain}", "keywords:"]
    lines += [f'  - "{k}"' for k in keywords]
    lines += ["google_news: true          # 키워드마다 구글 뉴스(한국어) 피드를 더한다",
              "filter_by_keywords: true   # 아래 feeds의 기사 중 키워드가 들어간 것만 남긴다", "language: ko",
              f"window_days: {window_days}             # 며칠 전 기사까지", "max_items: 30", 'output_dir: "reports"', "feeds:"]
    if feeds:
        for f in feeds:
            lines += [f'  - name: "{f["name"]}"', f'    url: "{f["url"]}"']
    else:
        lines[-1] = "feeds: []"
    lines += ["slack:", '  webhook_url: ""   # GitHub Secrets(SLACK_WEBHOOK_URL)나 환경변수로 넣는다. 여기에 주소를 적지 않는다',
              "  new_days: 1         # 며칠 안에 나온 기사를 Slack 목록에 넣을지(매일 실행이면 1)",
              "  max_headlines: 10   # Slack에 넣을 기사 수", ""]
    return "\n".join(lines)


def build(keywords: list[str], domain: str | None, out: Path, hhmm: str, window_days: int, force: bool) -> list[str]:
    if out.exists() and any(out.iterdir()):
        if not force:
            raise SystemExit(f"{out}가 비어 있지 않다. 다른 폴더를 쓰거나 --force")
        shutil.rmtree(out)
    shutil.copytree(TEMPLATE, out, ignore=shutil.ignore_patterns("__pycache__"))
    from profiles import GENERAL, detect, load_profiles, plan  # noqa: E402
    profs = load_profiles()
    name = domain or detect(keywords[0], profs)[0]
    p = plan(keywords[0], profs.get(name, GENERAL), datetime.now().date())
    feeds = [f for f in p["feeds"] if f["url"].startswith("https://") and "news.google.com" not in f["url"]]
    cron, note = kst_to_cron(hhmm)
    (out / "config.yaml").write_text(render_config(keywords, feeds, window_days, p["domain"]), encoding="utf-8")
    now = datetime.now(timezone.utc)
    subs = {"{{KEYWORD}}": ", ".join(keywords), "{{CRON}}": cron, "{{CRON_NOTE}}": note}
    subs.update({f"{{{{DATE_{i}}}}}": format_datetime(now - timedelta(hours=i)) for i in range(3)})  # 기간을 1일로 줄여도 시험 실행이 통과하게 몇 시간 전으로
    for rel in ("README.md", ".github/workflows/daily_collect.yml", "samples/sample_feed.xml"):
        f = out / rel
        t = f.read_text(encoding="utf-8")
        for k, v in subs.items():
            t = t.replace(k, v)
        f.write_text(t, encoding="utf-8")
    return [f"도메인 {p['domain']}, 피드 {len(feeds)}개 + 키워드별 구글 뉴스, {note}"]


def check(pkg: Path) -> list[str]:
    y = _yaml()
    probs = [f"필수 파일 없음: {r}" for r in REQUIRED if not (pkg / r).is_file()]
    if probs:
        return probs
    try:
        cfg = y.safe_load((pkg / "config.yaml").read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        return [f"config.yaml YAML 오류: {e}"]
    try:
        wf = y.safe_load((pkg / ".github/workflows/daily_collect.yml").read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        return [f"워크플로 YAML 오류: {e}"]
    on = wf.get("on", wf.get(True, {})) or {}  # PyYAML은 on:을 True로 읽는다
    crons = [c.get("cron", "") for c in (on.get("schedule") or []) if isinstance(c, dict)]
    if not crons or not all(re.fullmatch(r"\d{1,2} \d{1,2} \* \* [\d*,-]+", c) for c in crons):
        probs.append(f"워크플로 schedule cron이 없거나 형식이 틀렸다: {crons}")
    if "workflow_dispatch" not in on:
        probs.append("워크플로에 workflow_dispatch(수동 실행)가 없다")
    if (wf.get("permissions") or {}).get("contents") != "write":
        probs.append("워크플로 permissions.contents: write가 없다(보고서 커밋 실패)")
    wtext = (pkg / ".github/workflows/daily_collect.yml").read_text(encoding="utf-8")
    if "secrets.SLACK_WEBHOOK_URL" not in wtext:
        probs.append("워크플로가 SLACK_WEBHOOK_URL을 Secrets에서 전달하지 않는다")
    if "run_pipeline.py" not in wtext:
        probs.append("워크플로가 run_pipeline.py를 실행하지 않는다")
    if ((cfg.get("slack") or {}).get("webhook_url") or "") != "":
        probs.append("config.yaml의 slack.webhook_url이 비어 있지 않다(공개 저장소에 주소 노출)")
    if not cfg.get("keywords"):
        probs.append("config.yaml에 keywords가 없다")
    for f in pkg.rglob("*"):
        if f.is_file() and f.suffix in (".py", ".yaml", ".yml", ".md", ".txt", ".json") and WEBHOOK.search(f.read_text(encoding="utf-8", errors="replace")):
            probs.append(f"실제 Slack 웹훅 주소가 파일에 있다: {f.relative_to(pkg)}")
    sn = (pkg / "slack_notifier.py").read_text(encoding="utf-8")
    if not re.search(r"os\.environ\.get\(\s*[\"']SLACK_WEBHOOK_URL[\"']\s*\)\s*or", sn):
        probs.append("slack_notifier.py가 환경변수 SLACK_WEBHOOK_URL을 먼저 읽지 않는다")
    for f in pkg.rglob("*.py"):
        try:
            py_compile.compile(str(f), cfile=str(Path(tempfile.gettempdir()) / "dc_pc.pyc"), doraise=True)
        except py_compile.PyCompileError as e:
            probs.append(f"문법 오류: {f.relative_to(pkg)}: {e.msg[:120]}")
    return probs


def selftest(pkg: Path) -> list[str]:
    r = subprocess.run([sys.executable, "run_pipeline.py", "--offline-feed", "samples/sample_feed.xml", "--no-notify"], cwd=pkg,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    probs = []
    if "PIPELINE RUN OK" not in r.stdout:
        probs.append(f"시험 실행 실패: {(r.stdout + r.stderr)[-400:]}")
    reports = list((pkg / "reports").glob("*.md")) if (pkg / "reports").is_dir() else []
    if not reports:
        probs.append("시험 실행 후 reports/*.md가 없다")
    else:
        t = reports[0].read_text(encoding="utf-8")
        rows = [l for l in t.splitlines() if l.startswith("| ") and "example.com" in l]
        if len(rows) != 3:
            probs.append(f"예시 피드 5건 중 중복·기간 밖을 뺀 3건이어야 하는데 {len(rows)}건")
    for d in ("reports", "data"):
        shutil.rmtree(pkg / d, ignore_errors=True)
    shutil.rmtree(pkg / "__pycache__", ignore_errors=True)
    return probs


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="자동화 패키지 생성·검사")
    ap.add_argument("--keyword", action="append", default=[])
    ap.add_argument("--domain")
    ap.add_argument("--out")
    ap.add_argument("--time", default="09:00", help="한국 시각 HH:MM")
    ap.add_argument("--window-days", type=int, default=7)
    ap.add_argument("--zip", action="store_true")
    ap.add_argument("--no-selftest", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check")
    a = ap.parse_args(argv)
    if a.check:
        pkg = Path(a.check)
        probs = check(pkg)
        if not probs and not a.no_selftest:
            probs += selftest(pkg)
        for p in probs:
            print("FAIL:", p)
        print("PIPELINE FAILED" if probs else f"PIPELINE READY files={sum(1 for f in pkg.rglob('*') if f.is_file())} selftest="
              + ("skipped" if a.no_selftest else "ok"))
        return 1 if probs else 0
    keywords = [k.strip() for kw in a.keyword for k in kw.split(",") if k.strip()]
    if not keywords or not a.out:
        ap.error("--keyword와 --out이 필요하다")
    out = Path(a.out)
    for line in build(keywords, a.domain, out, a.time, a.window_days, a.force):
        print(line)
    probs = check(out)
    if not probs and not a.no_selftest:
        probs += selftest(out)
    for p in probs:
        print("FAIL:", p)
    if probs:
        print("PIPELINE FAILED")
        return 1
    for r in REQUIRED:
        print(f"  ✓ {r}")
    if a.zip:
        z = shutil.make_archive(str(out), "zip", root_dir=out.parent, base_dir=out.name)
        print(f"zip: {z}")
    print(f"PIPELINE READY files={sum(1 for f in out.rglob('*') if f.is_file())} selftest={'skipped' if a.no_selftest else 'ok'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
