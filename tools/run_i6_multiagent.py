#!/usr/bin/env python3
"""I6: split the review across specialists and merge the results.

Three reviewers look at the same pull request through one lens each -- security,
cost, reliability -- and a lead merges their findings into one review under the
same five-finding budget everything else in this project works to.

This is the orchestration hypothesis: that a task benefits from being decomposed
across focused agents. It was pre-registered as the experiment expected to be
removed, before any results existed. Every addition measured since has regressed,
which makes it more interesting to run rather than less: a stage predicted to
fail, in a project where everything failed, is only worth reporting if it was
actually measured.

    python tools/run_i6_multiagent.py --model haiku
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

LENSES = {
    "security": (
        "You are the security reviewer. Look only for changes that make something "
        "reachable that was not, or grant an identity more permission than it "
        "needs. Categories available to you: network-exposure, "
        "privilege-escalation. If this pull request raises nothing in your area, "
        "return no findings and say so -- that is a useful answer."
    ),
    "cost": (
        "You are the cost reviewer. Look only for changes that alter what this "
        "infrastructure costs to run, especially increases the pull request "
        "description does not mention. Category available to you: cost. If this "
        "pull request raises nothing in your area, return no findings and say so "
        "-- that is a useful answer."
    ),
    "reliability": (
        "You are the reliability reviewer. Look only for changes that risk data, "
        "remove a protection, or stop the system working as intended. Categories "
        "available to you: data-loss, guardrail, reliability. If this pull request "
        "raises nothing in your area, return no findings and say so -- that is a "
        "useful answer."
    ),
}

LEAD = (
    "You are the lead reviewer. Three specialists have each looked at this pull "
    "request through one lens. Their findings are below. Merge them into a single "
    "review: keep what genuinely matters to the person merging this, drop what "
    "does not, and rank what survives. A specialist reporting something is not a "
    "reason to keep it -- each of them saw only part of the picture, and none of "
    "them could weigh their area against the others. Apply the same five-finding "
    "budget and the same standard for suppression you would apply alone."
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="haiku", choices=list(M.MODELS))
    ap.add_argument("--effort", default="high")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--mode", default=None,
                    help="output directory name; for repeat runs")
    args = ap.parse_args()
    M.use_profile(args.profile)

    mode = args.mode or f"i6multi-{args.model}"
    out = ROOT / "results" / "findings" / mode
    traj = ROOT / "results" / "trajectories" / mode
    out.mkdir(parents=True, exist_ok=True)
    traj.mkdir(parents=True, exist_ok=True)

    who = M.whoami()
    print(f"  billing: profile {who['profile']}  account {who['account']}  "
          f"model {M.MODELS[args.model]}\n")

    ids = sorted(d.name.split("-")[1] for d in ROOT.glob("cases/case-*"))
    total_cost = 0.0

    for cid in ids:
        base = R.build_prompt(cid)
        t0, cost, specialists = time.time(), 0.0, {}

        for lens, instruction in LENSES.items():
            review, resp = M.call(base, model=args.model, effort=args.effort,
                                  system=M.review_instructions() + "\n\n## Your lens\n\n"
                                  + instruction)
            cost += M.usage_cost(resp, args.model)
            specialists[lens] = M.to_findings_json(review)

        reported = "\n\n".join(
            f"### {lens} reviewer\nverdict: {r['verdict']}\n{r['headline']}\n"
            + ("\n".join(f"- {f['address']} [{f['category']}/{f['severity']}] "
                         f"{f['explanation']}" for f in r["findings"])
               or "- (no findings)")
            for lens, r in specialists.items())

        merged, resp = M.call(base + "\n\n## Specialist reviews\n\n" + reported,
                              model=args.model, effort=args.effort,
                              system=M.review_instructions() + "\n\n## Your role\n\n" + LEAD)
        cost += M.usage_cost(resp, args.model)
        total_cost += cost
        elapsed = time.time() - t0

        payload = M.to_findings_json(merged)
        (out / f"{cid}.json").write_text(json.dumps(payload, indent=2))
        (traj / f"{cid}.json").write_text(json.dumps({
            "case": cid, "stage": "I6 multi-agent split",
            "model": M.MODELS[args.model], "aws_account": who["account"],
            "specialists": specialists, "merged": payload,
            "elapsed_s": round(elapsed, 1), "cost_usd": round(cost, 4),
        }, indent=2))

        raised = sum(len(r["findings"]) for r in specialists.values())
        print(f"  case {cid}: {payload['verdict']:<8} {len(payload['findings'])} kept "
              f"of {raised} raised  {elapsed:5.1f}s  ${cost:.4f}   "
              f"{payload['headline'][:42]}")

    print(f"\n  15 cases, ${total_cost:.2f}")
    print(f"  -> score with: python score.py --mode {mode}")


if __name__ == "__main__":
    main()
