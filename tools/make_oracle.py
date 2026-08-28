#!/usr/bin/env python3
"""Replay the labels back as findings, as a harness self-test.

This is not a measurement and no agent is involved. It answers one question:
does the scorer award a perfect score to a perfect answer, across every case?
Together with an empty run scoring 0.000, it shows the scorer discriminates in
both directions rather than being stuck at one end.

Being derived from the labels is the point -- it is tautological on purpose, in
the way a round-trip test is.

    python tools/make_oracle.py && python score.py --mode oracle   # 1.000
"""

import json
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "findings" / "oracle"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for d in sorted(ROOT.glob("cases/case-*")):
        cid = d.name.split("-")[1]
        labels = yaml.safe_load((d / "labels.yaml").read_text(encoding="utf-8")) or {}
        findings = [
            {
                "address": f["address"],
                "category": f["category"],
                "severity": f.get("severity", "unknown"),
                "evidence_ref": "labels.yaml",
            }
            for f in (labels.get("findings") or [])
            if f.get("category") != "noise"
        ]
        payload = {"verdict": labels.get("verdict"), "findings": findings}
        (OUT / f"{cid}.json").write_text(json.dumps(payload, indent=2))
        print(f"  case {cid}: {len(findings)} finding(s), verdict {payload['verdict']}")


if __name__ == "__main__":
    main()
