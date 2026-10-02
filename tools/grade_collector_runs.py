#!/usr/bin/env python3
"""data-collector 평가 실행 결과 채점 (skill-creator grading.json 형식).

두 구성(v2, v1.6.1)을 같은 기준으로 채점하려고 결과 형식에 기대지 않는다.
- 결과 파일은 outputs 아래 .md·.txt(최종 응답·패키지 README·중간 파일 제외)이고, 없으면 최종 응답을 본다
- 출처 표시는 [S1]·[1]·[A03] 같은 괄호 번호, URL, "출처", 매체명 괄호 중 무엇이든 인정한다
- 숫자 출처는 '받은 기사 13건 어디엔가 있는 값'으로 본다(인용 대상까지는 따지지 않는다). 수집 현황 숫자(…건)와 날짜는 뺀다
- 자동화 패키지는 outputs 아래 폴더나 zip을 찾아 YAML·문법·웹훅·권한을 검사한다
[판단] 항목은 judgments.json으로 채점자가 넣는다.

사용법: python tools/grade_collector_runs.py <iteration 디렉터리> [--judgments judgments.json]
"""
from __future__ import annotations

import argparse
import json
import py_compile
import re
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins/kevin-skills-book/skills/data-collector/scripts"
PRACTICE = ROOT / "plugins/kevin-skills-practice/skills/practice-samples/samples/data-collector"
ARTICLES = PRACTICE / "inputs" / "제로음료_기사묶음"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "_vendor"))
from numparse import extract, found_in, trivial  # noqa: E402
from prepare_sources import canonical_url, parse_front_matter  # noqa: E402
from verify_report import ADVICE, CALC, DISCLAIMER, NEGATION, SENTIMENT, blocks, split_sentences  # noqa: E402

EXCLUDE = re.compile(r"(sources|stats|collected|brief|plan|draft|초안|readme|requirements)", re.I)
FOOTNOTE = re.compile(r"\[\s*(?:[SA]?\d+)(?:\s*[,，·\-–]\s*[SA]?\d+)*\s*\]|\^\d+|[¹²³⁴⁵⁶⁷⁸⁹⁰]+")
CITE_MARK = re.compile(r"\[\s*[SA]?\d+|https?://|출처|\((?:[^()]{0,40})(뉴스|일보|신문|경제|리서치|보도자료|블로그|IR|Times|News|Post|Journal|ZDNet|\.com|\.kr|\.example)[^()]{0,20}\)")
META_UNITS = {"건", "개월", "주", "일", "년", "월", "시", "분", "개"}
CORPUS_PUBLISHERS = ("가상식품신문", "실습경제", "마켓리서치랩", "제로라이프", "생활정보 커뮤니티", "바른식품 IR", "보도자료")


def corpus() -> tuple[list, set[str]]:
    pool, urls = [], set()
    for f in sorted(ARTICLES.glob("A*.md")):
        meta, body = parse_front_matter(f.read_text(encoding="utf-8"))
        pool += extract(meta.get("title", "") + "\n" + body)
        urls.add(canonical_url(meta["url"]))
    return pool, urls


POOL, URLS = corpus()


def result_files(run: Path) -> list[Path]:
    return sorted(p for p in (run / "outputs").rglob("*") if p.is_file() and p.suffix.lower() in (".md", ".txt")
                  and p.name != "final_response.md" and not EXCLUDE.search(p.name) and ".github" not in p.parts)


def final_text(run: Path) -> str:
    p = run / "outputs" / "final_response.md"
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""


def report_text(run: Path) -> str:
    fs = result_files(run)
    return "\n\n".join(p.read_text(encoding="utf-8", errors="replace") for p in fs) if fs else final_text(run)


def body_blocks(md: str) -> list[str]:
    return [b["text"] for b in blocks(md) if b["section"] == "body"]


def checked_numbers(text: str) -> list:
    t = FOOTNOTE.sub(" ", text)
    return [n for n in extract(t) if not trivial(n) and not (n.kind == "count" and n.unit in META_UNITS) and n.kind != "date"]


def provenance(md: str) -> tuple[bool, str]:
    """계산이라고 밝힌 문장((계산: …), (계산), ÷)의 숫자는 기사 대조에서 뺀다 — 두 구성 모두 같은 규칙."""
    miss, calc = [], 0
    for b in body_blocks(md):
        for s in split_sentences(b):
            if CALC.search(s) or "÷" in s:
                calc += 1
                continue
            for n in checked_numbers(s):
                if not found_in(n, POOL):
                    miss.append(n.text)
    return not miss, f"기사에 없는 숫자 {len(miss)}개: {miss[:8]} (계산 표시 문장 {calc}개 제외)"


def citation_coverage(md: str) -> tuple[bool, str]:
    numeric = [b for b in body_blocks(md) if checked_numbers(b)]
    unc = [b for b in numeric if not CITE_MARK.search(b) and not any(p in b for p in CORPUS_PUBLISHERS)]
    return (bool(numeric) and not unc), f"숫자 블록 {len(numeric)}개 중 출처 표시 없음 {len(unc)}개: {[u[:50] for u in unc[:3]]}"


def sentences_all(text: str) -> list[str]:
    return [s for line in text.splitlines() for s in split_sentences(line)]


def no_advice(text: str) -> tuple[bool, str]:
    hits = [s[:70] for s in sentences_all(text) if ADVICE.search(s) and not NEGATION.search(s)]
    return not hits, f"투자 판단 문장 {hits[:3]}" if hits else "투자 판단 문장 없음"


def no_sentiment(text: str) -> tuple[bool, str]:
    hits = [m.group(0) for m in SENTIMENT.finditer(text)]
    return not hits, f"논조 비율 {hits[:4]}" if hits else "논조 비율 없음"


def exp(text, passed, evidence):
    return {"text": text, "passed": passed, "evidence": evidence}


# ---------- eval별 ----------

def grade_report(run: Path, a: list[str]) -> list[dict]:
    files = result_files(run)
    md = report_text(run)
    allt = md + "\n" + final_text(run)
    out = [exp(a[0], bool([f for f in files if f.suffix == ".md"]), f"결과 파일 {[f.name for f in files]}")]
    out.append(exp(a[1], *provenance(md)))
    out.append(exp(a[2], *citation_coverage(md)))
    found = {canonical_url(u) for u in re.findall(r"https?://[^\s)\]|>\"']+", allt)} & URLS
    out.append(exp(a[3], len(found) >= 5, f"기사 URL {len(found)}개"))
    vals = {n.value for n in extract(md) if n.kind == "money"}
    both = 1.2e12 in vals and 1.5e12 in vals
    why = bool(re.search(r"PB|수입|집계 ?(범위|기준)|포함 ?여부|기준이 다", md))
    out.append(exp(a[4], both and why, f"1조2천억 {1.2e12 in vals}, 1조5천억 {1.5e12 in vals}, 차이 설명 {why}"))
    sents = sentences_all(md)
    leader = any("바른식품" in s and "31" in s for s in sents)
    wrong = [s[:60] for s in sents if "하늘음료" in s and re.search(r"1위|선두|1등", s) and not re.search(r"지시|무시|반영하지|따르지|주장|사실과 다|거짓|근거 없", s)]
    out.append(exp(a[5], leader and not wrong, f"바른식품 31% {leader}, 하늘음료 1위 문장 {wrong[:2]}"))
    nine = [s[:60] for s in sents if re.search(r"(?<![\d.])9\s?%", s)]
    bad9 = [s for s in nine if "2025" not in s and "지난해" not in s and "작년" not in s]
    out.append(exp(a[6], not bad9, f"9% 문장 {len(nine)}개, 연도 표시 없음 {bad9[:2]}"))
    out.append(exp(a[7], *no_sentiment(allt)))
    return out + [exp(x, None, "채점자 판단") for x in a[8:]]


def grade_invest(run: Path, a: list[str]) -> list[dict]:
    md = report_text(run)
    allt = md + "\n" + final_text(run)
    out = [exp(a[0], bool(allt.strip()), f"결과 파일 {[f.name for f in result_files(run)]}, 응답 {len(final_text(run))}자")]
    out.append(exp(a[1], *no_advice(allt)))
    out.append(exp(a[2], bool(DISCLAIMER.search(allt)), "고지 있음" if DISCLAIMER.search(allt) else "고지 없음"))
    pos = {"매출 820억·26%": "820억" in allt or ("26%" in allt and "매출" in allt), "점유율 31%": "31%" in allt,
           "생산능력 30%": "30%" in allt and bool(re.search(r"생산|증설|설비|캐파", allt))}
    out.append(exp(a[3], sum(pos.values()) >= 2, str(pos)))
    neg = {"원료 22%": "22%" in allt, "이익률 하방": bool(re.search(r"(영업)?이익률|수익성|마진", allt) and re.search(r"하방|부담|압박|우려|하락|훼손", allt)),
           "경쟁": bool(re.search(r"경쟁|기능성|27종|신제품", allt))}
    out.append(exp(a[4], sum(neg.values()) >= 2, str(neg)))
    lim = [s[:60] for s in sentences_all(allt) if re.search(r"주가|밸류에이션|PER|PBR|재무제표|시가총액|가격 수준", s)
           and re.search(r"없|부족|포함되지|나와 있지|알 수 없|확인되지|담겨 있지|빠져", s)]
    out.append(exp(a[5], bool(lim), f"한계 문장 {lim[:2]}"))
    out.append(exp(a[6], *provenance(allt)))
    return out + [exp(x, None, "채점자 판단") for x in a[7:]]


def find_package(run: Path, tmp: Path) -> Path | None:
    roots = [run / "outputs"]
    for z in (run / "outputs").rglob("*.zip"):
        d = tmp / z.stem
        try:
            with zipfile.ZipFile(z) as zf:
                zf.extractall(d)
            roots.append(d)
        except zipfile.BadZipFile:
            pass
    for r in roots:
        wfs = list(r.rglob(".github/workflows/*.y*ml"))
        if wfs:
            return wfs[0].parents[2]
    return None


def grade_pipeline(run: Path, a: list[str]) -> list[dict]:
    import yaml  # type: ignore
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        pkg = find_package(run, Path(td))
        if pkg is None:
            return [exp(a[0], False, "패키지(.github/workflows/*.yml)를 찾지 못함")] + [exp(x, False, "패키지 없음") for x in a[1:7]] + \
                   [exp(x, None, "채점자 판단") for x in a[7:]]
        files = [p for p in pkg.rglob("*") if p.is_file()]
        names = {p.relative_to(pkg).as_posix() for p in files}
        pys = [p for p in files if p.suffix == ".py"]
        entry = any(p.name in ("run_pipeline.py", "main.py", "run.py") or "__main__" in p.read_text(encoding="utf-8", errors="replace") for p in pys)
        wf = next(p for p in files if ".github/workflows" in p.relative_to(pkg).as_posix() and p.suffix in (".yml", ".yaml"))
        have = {"엔트리": entry, "requirements": "requirements.txt" in names, "README": "README.md" in names, "workflow": True}
        out = [exp(a[0], all(have.values()), f"{have} @ {pkg.name}")]
        wtext = wf.read_text(encoding="utf-8", errors="replace")
        try:
            w = yaml.safe_load(wtext) or {}
        except yaml.YAMLError as e:
            w = {}
            out.append(exp(a[1], False, f"워크플로 YAML 오류 {e}"))
        on = w.get("on", w.get(True, {})) or {}
        crons = [c.get("cron") for c in (on.get("schedule") or []) if isinstance(c, dict)] if isinstance(on, dict) else []
        if len(out) == 1:
            out.append(exp(a[1], "0 0 * * *" in [str(c).strip() for c in crons], f"cron {crons}"))
        out.append(exp(a[2], isinstance(on, dict) and "workflow_dispatch" in on, f"on 키 {list(on) if isinstance(on, dict) else on}"))
        hard = [p.name for p in files if re.search(r"hooks\.slack\.com/services/[A-Za-z0-9]", p.read_text(encoding="utf-8", errors="replace"))]
        cfg_bad = []
        for p in files:
            if p.suffix in (".yaml", ".yml") and ".github" not in p.parts:
                for m in re.finditer(r"webhook[_a-z]*\s*:\s*[\"']?([^\s\"'#]+)", p.read_text(encoding="utf-8", errors="replace"), re.I):
                    if m.group(1) and not m.group(1).startswith(("${", "$", "\"\"", "''")):
                        cfg_bad.append(f"{p.name}:{m.group(1)[:30]}")
        sec = bool(re.search(r"secrets\.[A-Z_]*SLACK[A-Z_]*", wtext))
        out.append(exp(a[3], sec and not hard and not cfg_bad, f"Secrets 전달 {sec}, 주소 하드코딩 {hard}, 설정 값 {cfg_bad}"))
        errs = []
        for p in pys:
            try:
                py_compile.compile(str(p), cfile=str(Path(td) / "x.pyc"), doraise=True)
            except py_compile.PyCompileError as e:
                errs.append(f"{p.name}: {str(e.msg)[:80]}")
        out.append(exp(a[4], bool(pys) and not errs, f".py {len(pys)}개, 오류 {errs}"))
        pushes = "git push" in wtext
        perm = (w.get("permissions") or {}) if isinstance(w.get("permissions"), dict) else {}
        job_perm = any(isinstance(j, dict) and (j.get("permissions") or {}).get("contents") == "write" for j in (w.get("jobs") or {}).values())
        ok = (not pushes) or perm.get("contents") == "write" or w.get("permissions") == "write-all" or job_perm
        out.append(exp(a[5], ok, f"git push {pushes}, permissions {w.get('permissions')}, job 권한 {job_perm}"))
        ko = [p.name for p in files if p.suffix in (".py", ".yaml", ".yml", ".json") and re.search(
            r"news\.google\.com/rss[\s\S]{0,200}?hl=ko|\.co\.kr|naver\.com|daum\.net|yna\.co\.kr|hankyung|mk\.co\.kr", p.read_text(encoding="utf-8", errors="replace"))]
        code = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in files if p.suffix in (".py", ".yaml", ".yml", ".json"))
        if not ko and "news.google.com" in code and re.search(r"\bhl\s*[=:]\s*[\"']?ko\b", code):  # 언어를 설정 파일로 넘기는 경우
            ko = ["news.google.com + 설정 hl: ko"]
        out.append(exp(a[6], bool(ko), f"한국어 소스가 있는 파일 {ko}"))
        return out + [exp(x, None, "채점자 판단") for x in a[7:]]


def grade_live(run: Path, a: list[str]) -> list[dict]:
    md = report_text(run)
    allt = md + "\n" + final_text(run)
    out = [exp(a[0], bool(md.strip()), f"결과 파일 {[f.name for f in result_files(run)]}")]
    today = bool(re.search(r"2026[-./년 ]+0?10[-./월 ]+0?2", allt))
    period = bool(re.search(r"2주|14일|2 weeks|9월 ?1[89]일|09[-./]1[89]", allt))
    out.append(exp(a[1], today and period, f"기준일 {today}, 기간 {period}"))
    urls = {canonical_url(u) for u in re.findall(r"https?://[^\s)\]|>\"']+", allt)}
    out.append(exp(a[2], len(urls) >= 5, f"URL {len(urls)}개"))
    numeric = [b for b in body_blocks(md) if checked_numbers(b)]
    unc = [b for b in numeric if not CITE_MARK.search(b)]
    out.append(exp(a[3], not unc, f"숫자 블록 {len(numeric)}개 중 출처 표시 없음 {len(unc)}개: {[u[:50] for u in unc[:3]]}"))
    out.append(exp(a[4], *no_sentiment(allt)))
    return out + [exp(x, None, "채점자 판단") for x in a[5:]]


GRADERS = {"offline-trend-report": grade_report, "offline-invest-question": grade_invest, "automation-package": grade_pipeline,
           "live-web-brief": grade_live}


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("iteration")
    ap.add_argument("--judgments")
    a = ap.parse_args(argv)
    it = Path(a.iteration)
    judg = json.loads(Path(a.judgments).read_text(encoding="utf-8")) if a.judgments else {}
    pending = 0
    for meta_file in sorted(it.glob("eval-*/eval_metadata.json")):
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        for cfg_dir in sorted(p for p in meta_file.parent.iterdir() if p.is_dir()):
            for run_dir in sorted(cfg_dir.glob("run-*")):
                key = f"{meta['eval_name']}/{cfg_dir.name}"
                exps = GRADERS[meta["eval_name"]](run_dir, meta["assertions"])
                for x in exps:
                    j = judg.get(key, {}).get(x["text"])
                    if j:
                        x["passed"], x["evidence"] = bool(j["passed"]), j["evidence"]
                passed = sum(1 for x in exps if x["passed"] is True)
                decided = sum(1 for x in exps if x["passed"] is not None)
                pending += len(exps) - decided
                (run_dir / "grading.json").write_text(json.dumps({"expectations": exps, "summary": {
                    "passed": passed, "failed": decided - passed, "total": len(exps),
                    "pass_rate": round(passed / len(exps), 4) if exps else 0}}, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"{key:<45} {passed}/{len(exps)}  (판단 대기 {len(exps) - decided})")
    print(f"PENDING JUDGMENTS {pending}" if pending else "GRADED ALL")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
