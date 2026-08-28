#!/usr/bin/env python3
"""Baseline B1: one direct prompt over the diff and the pull request description.

No plan, no scanner output, no tools, no retries. This is what you get by asking
a capable model to review the change as a document, and it is the brief's own
suggested baseline.

It shares the review instructions and the output schema with the agent
(prompts/review.md, tools/model.py), so the only variable between this and later
stages is what information reaches the model. That is the experiment.

    python tools/run_oneshot.py --case 08          # one case
    python tools/run_oneshot.py --all              # all fifteen
    python tools/run_oneshot.py --all --model haiku  # cheap plumbing run
"""

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import model as M  # noqa: E402

ROOT = M.ROOT


def case_dir(cid):
    hits = list(ROOT.glob(f"cases/case-{cid}-*"))
    if not hits:
        sys.exit(f"no such case: {cid}")
    return hits[0]


def changed_resources(cid):
    """The plan, reduced to what it actually changes.

    The raw plan is ~145KB per case, almost all of it unchanged VPC attributes.
    Passing the whole file would bury the signal and cost 55x the tokens, so a
    real integration would pass this slice -- and so does I1.
    """
    plan = json.loads((ROOT / "results" / "plans" / f"{cid}.plan.json").read_text())
    return [c for c in plan.get("resource_changes", [])
            if c.get("change", {}).get("actions") != ["no-op"]]


def build_prompt(cid, with_plan=False):
    d = case_dir(cid)
    diff = (ROOT / "results" / "diffs" / f"{cid}.diff").read_text(encoding="utf-8", errors="replace")
    pr = (d / "pr_description.md").read_text(encoding="utf-8")
    prompt = (
        "Review this Terraform pull request.\n\n"
        "## Pull request description\n\n"
        f"{pr}\n\n"
        "## Diff\n\n"
        f"```diff\n{diff}\n```\n"
    )
    if with_plan:
        changes = changed_resources(cid)
        summary = "\n".join(
            f"  {'/'.join(c['change']['actions']):>16}  {c['address']}" for c in changes
        ) or "  (no resource changes)"
        prompt += (
            "\n## terraform plan\n\n"
            "Actions this change will take:\n\n"
            f"```\n{summary}\n```\n\n"
            "Full detail for each changed resource, from `terraform show -json`:\n\n"
            f"```json\n{json.dumps(changes, indent=2)}\n```\n"
        )
    return prompt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--model", default="sonnet", choices=list(M.MODELS))
    ap.add_argument("--effort", default="high")
    ap.add_argument("--profile", default=None,
                    help="AWS profile to bill; defaults to AWS_PROFILE or Joseph")
    ap.add_argument("--with-plan", action="store_true",
                    help="I1: also supply the plan's changed resources")
    ap.add_argument("--dry-run", action="store_true",
                    help="build the prompts and report their size without calling")
    ap.add_argument("--mode", default=None,
                    help="output directory name; defaults to oneshot, or "
                         "oneshot-<model> for anything but sonnet")
    args = ap.parse_args()
    M.use_profile(args.profile)

    stem = "i1plan" if args.with_plan else "oneshot"
    mode = args.mode or (stem if args.model == "sonnet" else f"{stem}-{args.model}")
    out = ROOT / "results" / "findings" / mode
    traj = ROOT / "results" / "trajectories" / mode
    out.mkdir(parents=True, exist_ok=True)
    traj.mkdir(parents=True, exist_ok=True)

    if args.all:
        ids = sorted(d.name.split("-")[1] for d in ROOT.glob("cases/case-*"))
    elif args.case:
        ids = [args.case]
    else:
        sys.exit("pass --case NN or --all")

    if args.dry_run:
        instructions = M.review_instructions()
        print(f"  system instructions: {len(instructions):,} chars")
        total = 0
        for cid in ids:
            p = build_prompt(cid, args.with_plan)
            total += len(p) + len(instructions)
            print(f"  case {cid}: prompt {len(p):>6,} chars  "
                  f"(~{(len(p)+len(instructions))/3.6/1000:.1f}k tokens)")
        print(f"\n  {len(ids)} case(s), ~{total/3.6/1000:.0f}k tokens total input")
        print(f"  estimated cost on sonnet: ${total/3.6*2.0/1e6 + len(ids)*3000*10.0/1e6:.2f}")
        return

    who = M.whoami()
    print(f"  billing: profile {who['profile']}  account {who['account']}  "
          f"model {M.MODELS[args.model]}\n")

    total_cost, total_s = 0.0, 0.0
    for cid in ids:
        prompt = build_prompt(cid, args.with_plan)
        t0 = time.time()
        review, response = M.call(prompt, model=args.model, effort=args.effort)
        elapsed = time.time() - t0
        cost = M.usage_cost(response, args.model)
        total_cost += cost
        total_s += elapsed

        (out / f"{cid}.json").write_text(json.dumps(M.to_findings_json(review), indent=2))
        (traj / f"{cid}.json").write_text(json.dumps({
            "case": cid,
            "stage": "I1 one-shot + plan" if args.with_plan else "B1 one-shot",
            "model": M.MODELS[args.model],
            "aws_account": who["account"],
            "effort": args.effort if args.model not in M.LEGACY_THINKING else None,
            "system": M.review_instructions(),
            "prompt": prompt,
            "response": M.to_findings_json(review),
            "usage": response.usage.model_dump() if hasattr(response.usage, "model_dump")
                     else dict(response.usage),
            "elapsed_s": round(elapsed, 1),
            "cost_usd": round(cost, 4),
        }, indent=2))

        print(f"  case {cid}: {review.verdict:<8} {len(review.findings)} finding(s)  "
              f"{elapsed:5.1f}s  ${cost:.4f}   {review.headline[:58]}")

    print(f"\n  {len(ids)} case(s), {total_s:.0f}s total, ${total_cost:.2f}")
    print(f"  -> results/findings/{mode}/    score with: python score.py --mode {mode}")


if __name__ == "__main__":
    main()
