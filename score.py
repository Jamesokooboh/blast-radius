#!/usr/bin/env python3
"""Score a run against the labels.

Scoring is set intersection on (resource address, category). No model grades
another model anywhere in this project, so the numbers are deterministic and a
second person re-running the same outputs gets the identical result.

A label with category "noise" is a finding the scanner reports that a good
reviewer suppresses. Reporting one is a false positive; staying quiet about it
is correct. That is what stops the agent from scoring well by simply reprinting
the linter.

    python score.py                 # every case
    python score.py --case 08
    python score.py --selfcheck     # the logic checks itself, no files needed
"""

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).parent
INDEX = re.compile(r"\[[^\]]*\]")

# ponytail: micro-averaged over findings, which weights busy cases more heavily.
# Switch to macro if the case set ever becomes lopsided.


def norm(address):
    """aws_security_group.web[0] and aws_security_group.web are one resource."""
    return INDEX.sub("", (address or "").strip()).lower()


def key(item):
    return (norm(item.get("address")), (item.get("category") or "").strip().lower())


def score_case(labels, findings):
    expected = {key(f) for f in labels.get("findings", []) if f.get("category") != "noise"}
    noise = {key(f) for f in labels.get("findings", []) if f.get("category") == "noise"}
    reported = {key(f) for f in findings.get("findings", [])}

    tp = expected & reported
    fn = expected - reported
    fp = reported - expected

    precision = len(tp) / len(reported) if reported else (1.0 if not expected else 0.0)
    recall = len(tp) / len(expected) if expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "band": labels.get("band", "?"),
        "tp": len(tp), "fp": len(fp), "fn": len(fn),
        "precision": precision, "recall": recall, "f1": f1,
        "reported": len(reported),
        "verdict_ok": findings.get("verdict") == labels.get("verdict"),
        "noise_total": len(noise),
        "noise_suppressed": len(noise - reported),
        "missed": sorted(f"{a}:{c}" for a, c in fn),
        "spurious": sorted(f"{a}:{c}" for a, c in fp),
    }


def aggregate(rows):
    tp = sum(r["tp"] for r in rows)
    fp = sum(r["fp"] for r in rows)
    fn = sum(r["fn"] for r in rows)
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    bands = {}
    for row in rows:
        b = bands.setdefault(row["band"], [0, 0])
        b[0] += row["tp"]
        b[1] += row["tp"] + row["fn"]
    return {
        "precision": p,
        "recall": r,
        "f1": 2 * p * r / (p + r) if (p + r) else 0.0,
        "verdict_accuracy": sum(x["verdict_ok"] for x in rows) / len(rows) if rows else 0.0,
        "findings_per_pr": sum(x["reported"] for x in rows) / len(rows) if rows else 0.0,
        "band_recall": {k: (v[0] / v[1] if v[1] else 1.0) for k, v in sorted(bands.items())},
        "noise_suppressed": sum(x["noise_suppressed"] for x in rows),
        "noise_total": sum(x["noise_total"] for x in rows),
    }


def load_yaml(path):
    import yaml
    return yaml.safe_load(path.read_text()) or {}


def case_dirs(only=None):
    for d in sorted(ROOT.glob("cases/case-*")):
        cid = d.name.split("-")[1]
        if only is None or cid == only:
            yield cid, d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case")
    ap.add_argument("--mode", default="agent", help="which run's findings to score")
    ap.add_argument("--selfcheck", action="store_true")
    args = ap.parse_args()

    if args.selfcheck:
        return selfcheck()

    rows, names = [], []
    for cid, d in case_dirs(args.case):
        labels = load_yaml(d / "labels.yaml")
        fpath = ROOT / "results" / "findings" / args.mode / f"{cid}.json"
        findings = json.loads(fpath.read_text()) if fpath.exists() else {"findings": []}
        rows.append(score_case(labels, findings))
        names.append((cid, d.name))

    if not rows:
        sys.exit("no cases found")

    print(f"\nmode: {args.mode}\n")
    print(f"{'case':<26} {'band':<5} {'TP':>3} {'FP':>3} {'FN':>3} {'F1':>6} {'verdict':>8}")
    print("-" * 62)
    for (cid, name), r in zip(names, rows):
        print(f"{name:<26} {r['band']:<5} {r['tp']:>3} {r['fp']:>3} {r['fn']:>3} "
              f"{r['f1']:>6.2f} {'ok' if r['verdict_ok'] else 'MISS':>8}")
        for m in r["missed"]:
            print(f"    missed:   {m}")
        for s in r["spurious"]:
            print(f"    spurious: {s}")

    agg = aggregate(rows)
    print("-" * 62)
    print(f"precision {agg['precision']:.3f}   recall {agg['recall']:.3f}   "
          f"F1 {agg['f1']:.3f}")
    print(f"verdict accuracy {agg['verdict_accuracy']:.3f}   "
          f"findings/PR {agg['findings_per_pr']:.1f}")
    print(f"band recall: " + "  ".join(f"{k}={v:.2f}" for k, v in agg['band_recall'].items()))
    if agg["noise_total"]:
        print(f"noise suppressed {agg['noise_suppressed']}/{agg['noise_total']}")

    out = ROOT / "report"
    out.mkdir(exist_ok=True)
    (out / f"metrics-{args.mode}.json").write_text(json.dumps(
        {"cases": dict(zip([n[0] for n in names], rows)), "aggregate": agg}, indent=2))
    return 0


def selfcheck():
    labels = {
        "band": "C",
        "verdict": "block",
        "findings": [
            {"address": "aws_db_instance.main", "category": "data-loss"},
            {"address": "aws_security_group.alb", "category": "noise"},
        ],
    }
    perfect = {"verdict": "block", "findings": [
        {"address": "aws_db_instance.main[0]", "category": "Data-Loss"}]}
    empty = {"verdict": "approve", "findings": []}
    parrot = {"verdict": "block", "findings": [
        {"address": "aws_db_instance.main", "category": "data-loss"},
        {"address": "aws_security_group.alb", "category": "noise"}]}

    p = score_case(labels, perfect)
    assert p["f1"] == 1.0, p
    assert p["verdict_ok"] and p["noise_suppressed"] == 1, p

    e = score_case(labels, empty)
    assert e["f1"] == 0.0 and not e["verdict_ok"], e

    # Reprinting the scanner's noise costs precision even though recall is perfect.
    q = score_case(labels, parrot)
    assert q["recall"] == 1.0 and q["precision"] == 0.5, q
    assert q["noise_suppressed"] == 0, q

    # A clean case with no findings: silence is a perfect score, noise is not.
    clean = {"band": "D", "verdict": "approve", "findings": []}
    assert score_case(clean, {"verdict": "approve", "findings": []})["f1"] == 1.0
    assert score_case(clean, {"verdict": "block", "findings": [
        {"address": "aws_vpc.main", "category": "invented"}]})["f1"] == 0.0

    agg = aggregate([p, e])
    assert 0.0 < agg["f1"] < 1.0, agg
    print("score selfcheck ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
