"""수집 → 집계 → 다이제스트 → (선택) Slack 알림을 차례로 실행한다.

  python run_pipeline.py                                  # 실제 수집
  python run_pipeline.py --offline-feed samples/sample_feed.xml --no-notify   # 네트워크 없이 시험 실행
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from analyzer import analyze
from collector import run_collection
from report_generator import generate
from slack_notifier import send_notification


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔에서도 한글이 깨지지 않게
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--offline-feed")
    ap.add_argument("--no-notify", action="store_true")
    a = ap.parse_args(argv)
    cfg = yaml.safe_load(Path(a.config).read_text(encoding="utf-8")) or {}
    collected = run_collection(cfg, a.offline_feed)
    Path("data").mkdir(exist_ok=True)
    Path("data/collected.json").write_text(json.dumps(collected, ensure_ascii=False, indent=2), encoding="utf-8")
    analysis = analyze(collected, cfg.get("keywords") or [])
    report = generate(collected, analysis, cfg, cfg.get("output_dir", "reports"))
    print(f"report: {report} ({analysis['count']}건)")
    for f in collected["feeds"]:
        print(f"  {f['feed']}: {f['status']} ({f['items']})")
    if not a.no_notify:
        print("slack:", send_notification(analysis, str(report), cfg, collected["items"]))
    ok = any(f["status"] == "ok" for f in collected["feeds"])
    print("PIPELINE RUN OK" if ok else "PIPELINE RUN FAILED: 모든 피드 수집 실패")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
