#!/usr/bin/env python3
"""Baseline A: the scanner that already runs in CI.

This is the status quo the project is measured against -- a static scan of the
Terraform, with no plan, no pull request description, and no notion of what the
change actually was. It reports on the whole stack every time, which is exactly
why teams stop reading it.

Scored generously on purpose. Checkov classifies problems by its own check ids,
not by this project's categories, so mapping them would either flatter or
penalise the baseline depending on how the table was written. Instead the
baseline is scored with `--match address`: naming the right resource counts as
finding the problem, however it labels it. That is the most favourable reading
of the scanner's output, and it is the number reported.

    python tools/run_checkov.py --all
    python score.py --mode checkov --match address
"""

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent


def scan(config_dir):
    """Run checkov over just the .tf files and return its failed checks."""
    with tempfile.TemporaryDirectory() as tmp:
        scan_dir = pathlib.Path(tmp) / "tf"
        scan_dir.mkdir()
        for f in config_dir.glob("*.tf"):
            shutil.copy2(f, scan_dir / f.name)

        exe = shutil.which("checkov")
        if not exe:
            sys.exit("checkov not on PATH -- pip install checkov")
        r = subprocess.run(
            [exe, "-d", str(scan_dir), "--framework", "terraform",
             "-o", "json", "--compact", "--quiet"],
            capture_output=True, text=True,
        )
        # checkov exits non-zero when checks fail, which is the normal case.
        if not r.stdout.strip():
            sys.exit(f"checkov produced no output for {config_dir}:\n{r.stderr}")
        out = json.loads(r.stdout)

    # Output is a list when several frameworks report, an object otherwise.
    blocks = out if isinstance(out, list) else [out]
    failed = []
    for b in blocks:
        failed.extend((b.get("results") or {}).get("failed_checks") or [])
    return failed


# Checkov classifies by its own check ids. To score it against this project's
# categories at all, the ids have to be mapped -- and the mapping is published
# here rather than buried, because it decides how well the baseline does.
#
# Every check that corresponds to a category this project labels is mapped.
# Everything else becomes "hygiene": a real observation about the stack that
# does not correspond to any problem in this pull request. Those are the
# findings a reviewer scrolls past.
CATEGORY = {
    # ingress open to the world, publicly reachable data stores, public buckets
    "CKV_AWS_24": "network-exposure",   # ingress from 0.0.0.0/0 on 22
    "CKV_AWS_25": "network-exposure",   # ingress from 0.0.0.0/0 on 3389
    "CKV_AWS_260": "network-exposure",  # ingress from 0.0.0.0/0 on 80
    "CKV_AWS_17": "network-exposure",   # RDS publicly accessible
    "CKV_AWS_20": "network-exposure",   # S3 bucket public read
    "CKV_AWS_53": "network-exposure",   # block public ACLs
    "CKV_AWS_54": "network-exposure",   # block public policy
    "CKV_AWS_55": "network-exposure",   # ignore public ACLs
    "CKV_AWS_56": "network-exposure",   # restrict public buckets
    "CKV_AWS_70": "network-exposure",   # bucket policy with any principal
    # over-broad IAM
    "CKV_AWS_1": "privilege-escalation",
    "CKV_AWS_62": "privilege-escalation",
    "CKV_AWS_63": "privilege-escalation",
    "CKV_AWS_286": "privilege-escalation",
    "CKV_AWS_287": "privilege-escalation",
    "CKV_AWS_288": "privilege-escalation",
    "CKV_AWS_289": "privilege-escalation",
    "CKV_AWS_290": "privilege-escalation",
    "CKV_AWS_355": "privilege-escalation",
    "CKV2_AWS_40": "privilege-escalation",
}

# Deliberately absent: nothing maps to data-loss, guardrail, cost or
# reliability, because Checkov has no check for any of them. That is the
# finding, not an oversight in this table.


def to_findings(failed, keep=None):
    """One finding per resource, taking its most specific category.

    `keep` restricts output to a set of resource addresses -- used for the
    scoped baseline, which reports only on what the pull request changed.
    """
    by_resource = {}
    for c in failed:
        address = c.get("resource") or ""
        if not address:
            continue
        if keep is not None and norm(address) not in keep:
            continue
        cat = CATEGORY.get(c.get("check_id", ""), "hygiene")
        prev = by_resource.get(address)
        # A mapped category beats "hygiene": if any check on this resource
        # names a real problem, that is what the scanner is saying about it.
        if prev is None or (prev["category"] == "hygiene" and cat != "hygiene"):
            by_resource[address] = {
                "address": address,
                "category": cat,
                "severity": "unknown",
                "check_id": c.get("check_id", ""),
                "evidence_ref": f"{c.get('file_path','')}:"
                                f"{(c.get('file_line_range') or [0])[0]} "
                                f"{c.get('check_name','')}",
            }
    return list(by_resource.values())


def norm(address):
    return address.split("[")[0].strip().lower()


def changed_resources(case_id):
    """Addresses the plan actually touches, for the scoped baseline."""
    p = ROOT / "results" / "plans" / f"{case_id}.plan.json"
    if not p.exists():
        sys.exit(f"{p} missing -- run ./plan.sh {case_id} first")
    plan = json.loads(p.read_text())
    return {
        norm(c["address"])
        for c in plan.get("resource_changes", [])
        if c.get("change", {}).get("actions") != ["no-op"]
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--scoped", action="store_true",
                    help="report only on resources the plan changes, as a "
                         "diff-aware CI integration would")
    args = ap.parse_args()

    mode = "checkov-scoped" if args.scoped else "checkov"
    out_dir = ROOT / "results" / "findings" / mode
    out_dir.mkdir(parents=True, exist_ok=True)

    ids = []
    if args.all:
        ids = sorted(d.name.split("-")[1] for d in ROOT.glob("cases/case-*"))
    elif args.case:
        ids = [args.case]
    else:
        sys.exit("pass --case NN or --all")

    total = 0
    for cid in ids:
        work = ROOT / ".work" / cid
        if not work.exists():
            sys.exit(f"{work} missing -- run ./plan.sh {cid} first")
        keep = changed_resources(cid) if args.scoped else None
        findings = to_findings(scan(work), keep)
        total += len(findings)
        # The scanner has no verdict. It fails the build whenever anything is
        # wrong anywhere in the stack, which on this fixture is always.
        payload = {
            "verdict": "block" if findings else "approve",
            "findings": findings,
        }
        (out_dir / f"{cid}.json").write_text(json.dumps(payload, indent=2))
        print(f"  case {cid}: {len(findings)} resources flagged")

    print(f"\n  {total / len(ids):.1f} flagged resources per pull request on average")


if __name__ == "__main__":
    main()
