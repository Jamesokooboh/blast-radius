#!/usr/bin/env python3
"""I5: carry review decisions forward between pull requests.

The fifteen cases are successive pull requests against one stack, so a reviewer
would accumulate context: having decided in one review that the marketing bucket
is public on purpose, they would not relitigate it in the next. This runs the
cases in order and gives each one a short record of what was decided before it.

The memory holds decisions, not findings -- verdict, headline, and what the
reviewer chose to say nothing about. That is what a person would carry.

    python tools/run_i5_memory.py --model haiku
"""

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import model as M  # noqa: E402
import run_oneshot as R  # noqa: E402

ROOT = M.ROOT


def memory_block(entries):
    if not entries:
        return ""
    lines = []
    for e in entries:
        lines.append(f"- PR #{e['case']}: {e['verdict']} — {e['headline']}")
        if e.get("suppressed"):
            lines.append(f"    chose not to raise: {e['suppressed'][:220]}")
    return (
        "\n## Earlier reviews of this stack\n\n"
        "Decisions you have already made on previous pull requests against this\n"
        "same infrastructure. Do not relitigate a question that has been settled,\n"
        "and do not treat a past decision as binding if this change alters the\n"
        "facts behind it.\n\n"
        + "\n".join(lines) + "\n"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="haiku", choices=list(M.MODELS))
    ap.add_argument("--effort", default="high")
    ap.add_argument("--profile", default=None)
    args = ap.parse_args()
    M.use_profile(args.profile)

    mode = f"i5memory-{args.model}"
    out = ROOT / "results" / "findings" / mode
    traj = ROOT / "results" / "trajectories" / mode
    out.mkdir(parents=True, exist_ok=True)
    traj.mkdir(parents=True, exist_ok=True)

    who = M.whoami()
    print(f"  billing: profile {who['profile']}  account {who['account']}  "
          f"model {M.MODELS[args.model]}\n")

    ids = sorted(d.name.split("-")[1] for d in ROOT.glob("cases/case-*"))
    entries, total_cost = [], 0.0

    for cid in ids:
        prompt = R.build_prompt(cid) + memory_block(entries)
        t0 = time.time()
        review, response = M.call(prompt, model=args.model, effort=args.effort)
        elapsed = time.time() - t0
        cost = M.usage_cost(response, args.model)
        total_cost += cost

        payload = M.to_findings_json(review)
        (out / f"{cid}.json").write_text(json.dumps(payload, indent=2))
        (traj / f"{cid}.json").write_text(json.dumps({
            "case": cid, "stage": "I5 one-shot + review memory",
            "model": M.MODELS[args.model], "aws_account": who["account"],
            "memory_entries": len(entries), "prompt": prompt,
            "response": payload, "elapsed_s": round(elapsed, 1),
            "cost_usd": round(cost, 4),
        }, indent=2))

        entries.append({"case": cid, "verdict": review.verdict,
                        "headline": review.headline,
                        "suppressed": review.suppressed})

        print(f"  case {cid}: {review.verdict:<8} {len(review.findings)} finding(s)  "
              f"mem={len(entries)-1:<2} {elapsed:5.1f}s  ${cost:.4f}   "
              f"{review.headline[:46]}")

    print(f"\n  15 cases, ${total_cost:.2f}")
    print(f"  -> score with: python score.py --mode {mode}")


if __name__ == "__main__":
    main()
