#!/usr/bin/env python3
"""Turn a raw `terraform show -json` dump into the plan the agent actually sees.

Strips phantom updates (see planfilter) and writes a short summary of the real
actions next to it, so a reader can tell at a glance what the plan does.
"""

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import planfilter  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    plan = json.loads(pathlib.Path(args.raw).read_text())
    plan, dropped = planfilter.strip_phantoms(plan)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2))

    actions = planfilter.real_changes(plan)
    summary = out.with_suffix(".summary.txt")
    lines = [f"{act:>18}  {addr}" for addr, act in actions] or ["(no changes)"]
    if dropped:
        lines.append(f"\ndropped {len(dropped)} phantom update(s): {', '.join(dropped)}")
    summary.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
