#!/usr/bin/env python3
"""I3: drop any finding that cannot be tied to something real.

A finding survives if the resource it names is in the plan's change set, or if
that resource appears in the pull request's diff. Anything else is a claim about
something this pull request did not touch, or about a resource that does not
exist, and it is removed.

This is verification, not review: it only ever removes findings, so it cannot
invent recall. It also costs nothing -- no model call is involved, which is the
point. If a technique can be made deterministic it should be.

    python tools/verify_citations.py --from oneshot-haiku
"""

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = re.compile(r"\[[^\]]*\]")
VAR_PREFIX = re.compile(r"^(var|variable)\.")


def norm(a):
    return VAR_PREFIX.sub("", INDEX.sub("", (a or "").strip()).lower())


def evidence_for(cid):
    """What this pull request can legitimately be said to be about."""
    plan = json.loads((ROOT / "results" / "plans" / f"{cid}.plan.json").read_text())
    changed = {norm(c["address"]) for c in plan.get("resource_changes", [])
               if c.get("change", {}).get("actions") != ["no-op"]}
    diff = (ROOT / "results" / "diffs" / f"{cid}.diff").read_text(
        encoding="utf-8", errors="replace").lower()
    return changed, diff


def supported(address, changed, diff):
    a = norm(address)
    if a in changed:
        return True
    if a and a in diff:
        return True
    # `aws_s3_bucket.data` -> does "data" appear as a resource name in the diff?
    tail = a.rsplit(".", 1)[-1]
    return bool(tail) and re.search(rf'"{re.escape(tail)}"', diff) is not None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", default="oneshot-haiku")
    ap.add_argument("--to", dest="dst", default=None)
    args = ap.parse_args()
    dst = args.dst or args.src.replace("oneshot", "i3verify")

    src_dir = ROOT / "results" / "findings" / args.src
    out_dir = ROOT / "results" / "findings" / dst
    out_dir.mkdir(parents=True, exist_ok=True)

    kept = dropped = 0
    for f in sorted(src_dir.glob("*.json")):
        cid = f.stem
        changed, diff = evidence_for(cid)
        d = json.loads(f.read_text())
        survivors = []
        for x in d.get("findings", []):
            if supported(x["address"], changed, diff):
                survivors.append(x)
                kept += 1
            else:
                dropped += 1
                print(f"  case {cid}: dropped {x['address']} [{x['category']}] "
                      f"-- not in the plan's change set or the diff")
        d["findings"] = survivors
        (out_dir / f.name).write_text(json.dumps(d, indent=2))

    print(f"\n  {kept} finding(s) kept, {dropped} dropped, $0.00")
    print(f"  -> score with: python score.py --mode {dst}")


if __name__ == "__main__":
    main()
