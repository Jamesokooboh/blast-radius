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
# A Terraform input variable is legitimately written three ways. They name the
# same thing, and which one a reviewer picks says nothing about review quality.
VAR_PREFIX = re.compile(r"^(var|variable)\.")

# ponytail: micro-averaged over findings, which weights busy cases more heavily.
# Switch to macro if the case set ever becomes lopsided.


def norm(address):
    """aws_security_group.web[0] and aws_security_group.web are one resource.

    Likewise var.x, variable.x and x are one input variable.
    """
    a = INDEX.sub("", (address or "").strip()).lower()
    return VAR_PREFIX.sub("", a)


MATCH = "strict"  # "strict" = address and category; "address" = address only


def key(item):
    cat = "" if MATCH == "address" else (item.get("category") or "").strip().lower()
    return (norm(item.get("address")), cat)


def group(label_finding):
    """The set of addresses that count as naming this problem.

    One problem often spans several resources -- both subnet associations moved
    to the same route table, three resources added for one NAT gateway. A
    reviewer who reports that once, against any of them, has found it. `also`
    lists the equally acceptable addresses; naming several is neither rewarded
    nor punished, since they are the same finding.
    """
    cat = "" if MATCH == "address" else (label_finding.get("category") or "").strip().lower()
    addrs = [label_finding.get("address")] + list(label_finding.get("also") or [])
    return {(norm(a), cat) for a in addrs if a}


def score_case(labels, findings):
    all_labels = labels.get("findings", []) or []
    expected = [group(f) for f in all_labels if f.get("category") != "noise"]
    noise = [group(f) for f in all_labels if f.get("category") == "noise"]
    reported = {key(f) for f in findings.get("findings", []) or []}

    remaining = set(reported)
    tp, missed = 0, []
    for g in expected:
        if remaining & g:
            tp += 1
            remaining -= g
        else:
            missed.append(sorted(g)[0])

    # Reprinting a finding the reviewer should have suppressed is a false
    # positive, and it is the one this project most wants to catch. Noise
    # matches on address alone: raising that resource at all is the mistake,
    # whatever category the reporter files it under.
    parroted = []
    for g in noise:
        addrs = {a for a, _ in g}
        hits = {k for k in remaining if k[0] in addrs}
        if hits:
            parroted.append(sorted(hits)[0])
            remaining -= hits

    fp = len(remaining) + len(parroted)
    fn = len(missed)

    precision = tp / (tp + fp) if (tp + fp) else (1.0 if not expected else 0.0)
    recall = tp / len(expected) if expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "band": labels.get("band", "?"),
        "tp": tp, "fp": fp, "fn": fn,
        "precision": precision, "recall": recall, "f1": f1,
        "reported": len(reported),
        "verdict_ok": findings.get("verdict") == labels.get("verdict"),
        "noise_total": len(noise),
        "noise_suppressed": len(noise) - len(parroted),
        "missed": sorted(f"{a}:{c}" for a, c in missed),
        "spurious": sorted(f"{a}:{c}" for a, c in (list(remaining) + parroted)),
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
    ap.add_argument("--match", choices=("strict", "address"), default="strict",
                    help="address: credit a finding that names the right resource "
                         "however it classifies it. Used for the scanner baseline.")
    ap.add_argument("--selfcheck", action="store_true")
    args = ap.parse_args()

    global MATCH
    MATCH = args.match

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

    # The three ways of writing an input variable are one address.
    varlabels = {"band": "C", "verdict": "block", "findings": [
        {"address": "app_data_bucket_arns", "category": "privilege-escalation"}]}
    for form in ("app_data_bucket_arns", "var.app_data_bucket_arns",
                 "variable.app_data_bucket_arns"):
        r = score_case(varlabels, {"verdict": "block", "findings": [
            {"address": form, "category": "privilege-escalation"}]})
        assert r["f1"] == 1.0, (form, r)

    # Noise is matched by address, so miscategorising it does not launder it.
    miscategorised = score_case(labels, {"verdict": "block", "findings": [
        {"address": "aws_db_instance.main", "category": "data-loss"},
        {"address": "aws_security_group.alb", "category": "network-exposure"}]})
    assert miscategorised["noise_suppressed"] == 0, miscategorised
    assert miscategorised["fp"] == 1, miscategorised

    # A clean case with no findings: silence is a perfect score, noise is not.
    clean = {"band": "D", "verdict": "approve", "findings": []}
    assert score_case(clean, {"verdict": "approve", "findings": []})["f1"] == 1.0
    assert score_case(clean, {"verdict": "block", "findings": [
        {"address": "aws_vpc.main", "category": "invented"}]})["f1"] == 0.0

    agg = aggregate([p, e])
    assert 0.0 < agg["f1"] < 1.0, agg

    # One problem across several resources: naming any one of them finds it,
    # naming all of them is not punished, naming none is a miss.
    spread = {"band": "C", "verdict": "block", "findings": [
        {"address": "aws_route_table_association.private_a",
         "also": ["aws_route_table_association.private_b"],
         "category": "network-exposure"}]}
    one = score_case(spread, {"verdict": "block", "findings": [
        {"address": "aws_route_table_association.private_b", "category": "network-exposure"}]})
    assert one["f1"] == 1.0, one
    both = score_case(spread, {"verdict": "block", "findings": [
        {"address": "aws_route_table_association.private_a", "category": "network-exposure"},
        {"address": "aws_route_table_association.private_b", "category": "network-exposure"}]})
    assert both["f1"] == 1.0 and both["fp"] == 0, both
    neither = score_case(spread, {"verdict": "block", "findings": [
        {"address": "aws_vpc.main", "category": "network-exposure"}]})
    assert neither["tp"] == 0 and neither["fp"] == 1, neither

    print("score selfcheck ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
