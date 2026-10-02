#!/usr/bin/env python3
"""V4: 로컬 영상+자막 → 쇼츠 끝까지 만들기(한글 자막·후크), verify_short 통과, 결함 영상(해상도·길이·무음·검은 화면·없음)은 검출.
카드뉴스 렌더러가 한글 폰트로 카드 PNG와 카드 쇼츠를 만드는지도 확인한다. ffmpeg가 필요하다."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shorts_fixtures import KEY, SCRIPTS, SRT, VIDEO, good_highlights, run_script  # noqa: E402
sys.path.insert(0, str(SCRIPTS))

import media  # noqa: E402

results: list[tuple[str, bool, str]] = []


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ff = media.ffmpeg_path()
    if not ff:
        print("FFMPEG MISSING")
        print("SHORTS E2E FAILED")
        return 1
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        W = Path(td) / "작업 폴더"  # 공백·한글 경로(Windows 필터 이스케이프 확인)
        r = run_script("prepare_source.py", "--video", VIDEO, "--subs", SRT, "--output", W)
        results.append(("1단계 원본·대본 준비", "SOURCE READY type=video" in r.stdout and (W / "transcript.json").is_file(), r.stdout[-200:] + r.stderr[-200:]))
        r = run_script("select_highlights.py", "--transcript", W / "transcript.json", "--output", W / "candidates.json", "--mode", "candidates")
        results.append(("2단계 후보", (W / "candidates.json").is_file() and json.loads((W / "candidates.json").read_text(encoding="utf-8")) != [],
                        r.stdout[-200:] + r.stderr[-200:]))
        hl = good_highlights(("xlookup",))
        (W / "highlights.json").write_text(json.dumps(hl, ensure_ascii=False), encoding="utf-8")
        r = run_script("validate_highlights.py", W / "highlights.json", "--source", W / "source.json", "--transcript", W / "transcript.json")
        results.append(("4단계 하이라이트 검사", "HIGHLIGHTS OK" in r.stdout, r.stdout[-300:]))
        r = run_script("generate_shorts.py", "--highlights", W / "highlights.json", "--video", VIDEO, "--output", W / "shorts",
                       "--srt", W / "transcript.srt", cwd=W)
        out = W / "shorts" / "short_01.mp4"
        results.append(("5단계 쇼츠 생성", out.is_file() and "성공 1개" in r.stdout, r.stdout[-400:] + r.stderr[-300:]))
        r = run_script("verify_short.py", W / "shorts", "--highlights", W / "highlights.json")
        results.append(("6단계 완성 검사 통과", "SHORTS VERIFY OK n=1" in r.stdout, r.stdout[-400:]))
        log = W / "output" / "logs"
        results.append(("ffmpeg 오류 로그 없음(자막·후크 합성 성공)", not log.is_dir() or not any(log.iterdir()),
                        str(list(log.iterdir())) if log.is_dir() else ""))
        meta = json.loads((W / "shorts" / "metadata.json").read_text(encoding="utf-8"))
        results.append(("metadata 제목·설명", meta["shorts"][0]["title"] == hl[0]["title"] and "#shorts" in meta["shorts"][0]["description"], ""))
        tags = meta["shorts"][0]["hashtags"]
        whole = "#" + "".join(ch for ch in hl[0]["title"] if ch.isalnum())[:20]
        results.append(("해시태그: 제목 전체를 붙인 긴 태그 없음", whole not in tags and len(tags) <= 5, str(tags)))
        # 같은 명령 다시 실행 → 완성본은 건너뜀(시간 제한 환경 재실행 안전)
        r = run_script("generate_shorts.py", "--highlights", W / "highlights.json", "--video", VIDEO, "--output", W / "shorts", cwd=W)
        results.append(("재실행 시 완성본 건너뜀", "이미 존재" in r.stdout, r.stdout[-200:]))

        # verify_short 대조: 결함 영상
        B = Path(td) / "bad"
        B.mkdir()
        bad_hl = [{"index": i, "start": 0, "end": 20, "title": "t", "hook": "h", "subtitles": []} for i in range(1, 5)]
        (B / "h.json").write_text(json.dumps(bad_hl), encoding="utf-8")
        mk = lambda args, name: subprocess.run([ff, "-y", "-loglevel", "error", *args, str(B / name)], check=True)  # noqa: E731
        mk(["-f", "lavfi", "-i", "testsrc=size=720x1280:rate=10", "-f", "lavfi", "-i", "sine", "-t", "20", "-shortest"], "short_01.mp4")
        mk(["-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=10", "-t", "20"], "short_02.mp4")
        mk(["-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=10", "-f", "lavfi", "-i", "sine", "-t", "20", "-shortest"], "short_03.mp4")
        (B / "metadata.json").write_text(json.dumps({"shorts": [{"index": 3, "overlay": False}]}), encoding="utf-8")
        r = run_script("verify_short.py", B, "--highlights", B / "h.json", "--json")
        try:
            got = json.loads(r.stdout[: r.stdout.rindex("SHORTS VERIFY")])["errors"]
        except ValueError:
            got = []
        by = {(e["where"], e["check"]) for e in got}
        for name, key in (("해상도 결함 검출", ("short_01.mp4", "resolution")), ("오디오 없음 검출", ("short_02.mp4", "audio")),
                          ("검은 화면 검출", ("short_03.mp4", "black")), ("파일 없음 검출", ("short_04.mp4", "missing")),
                          ("오버레이 합성 실패 표시 검출", ("short_03.mp4", "overlay"))):
            results.append((name, key in by, str(sorted(by))))
        long_hl = [{"index": 1, "start": 0, "end": 80, "title": "t", "hook": "h", "subtitles": []}]
        shutil.copy(B / "short_03.mp4", B / "keep.mp4")
        mk(["-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=5", "-f", "lavfi", "-i", "sine", "-t", "80", "-shortest"], "short_01.mp4")
        (B / "long.json").write_text(json.dumps(long_hl), encoding="utf-8")
        r = run_script("verify_short.py", B, "--highlights", B / "long.json")
        results.append(("60초 초과 검출", "[duration]" in r.stdout, r.stdout[-200:]))

        # 두 줄 후크의 줄 간격: textfile을 CRLF로 쓰면 drawtext가 빈 줄을 하나 더 넣는다(Windows 텍스트 모드)
        import generate_shorts as gs  # noqa: E402
        from PIL import Image

        def hook_gap(writer) -> int:
            txt, png = Path(td) / "hook.txt", Path(td) / "hook.png"
            writer(txt)
            vf = gs.build_hook_drawtext(str(txt), gs.get_font_path(), 64, 3)
            subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=gray:s=1080x1920:d=1", "-vf", vf,
                            "-frames:v", "1", str(png)], check=True)
            im = Image.open(png).convert("L")
            px = im.load()
            rows = [y for y in range(im.height) if any(px[x, y] > 230 for x in range(0, im.width, 2))]
            gaps = [b - a for a, b in zip(rows, rows[1:]) if b - a > 1]
            return max(gaps) if gaps else -1
        two = "보고서 수정 2시간이" + chr(10) + "30분으로"
        lf = hook_gap(lambda p: gs.write_drawtext_file(str(p), two))
        crlf = hook_gap(lambda p: p.write_bytes(two.replace(chr(10), chr(13) + chr(10)).encode("utf-8")))
        results.append(("두 줄 후크 줄 간격이 글자 크기보다 작다", 0 < lf < 64, f"간격 {lf}px"))
        results.append(("양성 대조: CRLF 후크 파일이면 빈 줄 간격 검출", crlf >= 64, f"간격 {crlf}px"))

        # 카드뉴스: 한글 폰트로 카드 1장 + 2초 카드 쇼츠
        C = Path(td) / "cards"
        C.mkdir()
        cards = {"series_label": "실습 · 카드", "footer": "끝", "cards": [{"index": 1, "title_lines": ["표로 바꾸면", "편해진다"], "punch": "Ctrl+T",
                                                                          "points": [{"label": "자동", "body": "새 행에 수식이 따라온다"}]}]}
        (C / "cards.json").write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
        r = run_script("card_news.py", "--cards", C / "cards.json", "--output", C / "out", "--video", C / "out" / "c.mp4", "--seconds", "2")
        pngs = list((C / "out").glob("*.png")) if (C / "out").is_dir() else []
        info = media.probe(str(C / "out" / "c.mp4"))
        # 굵은 글꼴에 외곽선을 더하면 획 많은 한글(를·름·셀)이 덩어리가 된다 → 획 수(세로 방향 잉크 구간 수)로 잰다
        import card_news as cn  # noqa: E402
        from PIL import Image, ImageDraw
        def strokes(ch: str, stroke: int) -> int:
            f = cn.get_font(120)
            im = Image.new("L", (240, 240), 0)
            ImageDraw.Draw(im).text((40, 40), ch, font=f, fill=255, stroke_width=stroke, stroke_fill=255)
            bb, px, best = im.getbbox(), im.load(), 0
            for x in range(bb[0], bb[2]):
                n, prev = 0, False
                for y in range(bb[1], bb[3]):
                    on = px[x, y] >= 128
                    n += on and not prev
                    prev = on
                best = max(best, n)
            return best
        clean = {ch: strokes(ch, 0) for ch in "를름셀"}
        used = {ch: strokes(ch, cn.title_stroke(3)) for ch in "를름셀"}
        results.append(("카드 제목: 획 많은 한글이 뭉개지지 않음", used == clean, f"외곽선 {cn.title_stroke(3)}: {used} / 원래 {clean}"))
        results.append(("양성 대조: 두꺼운 외곽선이면 획 뭉개짐 검출", any(strokes(ch, 6) < clean[ch] for ch in clean), ""))
        results.append(("카드뉴스 PNG·카드 쇼츠", bool(pngs) and (info["width"], info["height"]) == (1080, 1920) and "한글 폰트를 찾지 못했다" not in r.stdout,
                        r.stdout[-300:] + r.stderr[-200:]))
    bad = [x for x in results if not x[1]]
    for name, ok, why in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f" — {why}"))
    if bad:
        print(f"SHORTS E2E FAILED ({len(bad)}/{len(results)})")
        return 1
    print(f"SHORTS E2E OK — {len(results)}개 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
