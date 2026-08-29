#!/usr/bin/env python3
"""Review a Terraform change and print a pull request comment.

This is the configuration that won the evaluation in report/changelog.md: one
prompt, the diff, the description, and nothing else. It uses prompts/review.md
verbatim -- the same instructions scored against 15 labelled pull requests -- so
the tool and the measurement cannot drift apart.

Two design decisions come straight out of that evaluation rather than taste:

  It never runs `terraform plan`. Supplying the plan dropped F1 from 0.784 to
  0.674 across four runs each, with no overlap. So this needs no state access,
  no cloud credentials in CI, and no init step.

  It comments, it does not block. Verdict accuracy never exceeded 0.733 in any
  configuration measured, which is not good enough to fail somebody's build.
  The verdict is advice; the findings are the product.

    python review.py                                  # working tree vs main
    python review.py --repo ../my-infra --base develop
    python review.py --diff saved.diff --description pr.md
    python review.py --json                           # machine-readable
"""

import argparse
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent / "tools"))
import model as M  # noqa: E402

# The comment is UTF-8 markdown bound for GitHub; a Windows console defaults to
# cp1252 and would crash on the verdict icons.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# A runaway diff (a vendored module, a generated file, a rebase gone wrong) is
# both expensive and worse to review than its first few hunks. Roughly 30k
# tokens of diff, which no measured case came close to.
MAX_DIFF_CHARS = 120_000

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
VERDICT_NOTE = {
    "block": "Do not merge without addressing the finding above.",
    "warn": "Mergeable, but the author should see this first.",
    "approve": "Nothing here needs the reviewer's attention.",
}


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r.stdout


def terraform_diff(repo, base):
    """The Terraform part of the change, and nothing else.

    Restricting to *.tf keeps the reviewer on infrastructure and keeps the
    prompt small; a pull request that also touches application code should not
    spend the five-finding budget on it.
    """
    repo = pathlib.Path(repo).resolve()
    if not (repo / ".git").exists():
        sys.exit(f"{repo} is not a git repository")

    # Prefer the merge base, so the diff shows this branch's work rather than
    # everything that landed on the base branch meanwhile.
    merge_base = git(repo, "merge-base", "HEAD", base).strip() if base else ""
    spec = [merge_base] if merge_base else []
    diff = git(repo, "diff", *spec, "--", "*.tf", "*.tfvars")
    if not diff.strip():
        diff = git(repo, "diff", "--cached", *spec, "--", "*.tf", "*.tfvars")
    return diff


def cap_diff(diff, limit=MAX_DIFF_CHARS):
    """Truncate an oversized diff at a hunk boundary, and say so."""
    if len(diff) <= limit:
        return diff
    cut = diff.rfind("\n@@ ", 0, limit)
    if cut <= 0:  # no hunk header early enough; fall back to a line boundary
        cut = diff.rfind("\n", 0, limit)
    kept = diff[:cut] if cut > 0 else diff[:limit]
    return (kept + "\n\n[diff truncated: %d of %d characters shown. Review "
            "what is here and say in the headline that the change was too "
            "large to read in full.]\n" % (len(kept), len(diff)))


def build_prompt(diff, description):
    parts = ["Review this Terraform pull request.\n"]
    if description:
        parts.append(f"## Pull request description\n\n{description}\n")
    else:
        parts.append("## Pull request description\n\n"
                     "(none supplied -- judge the change on its own terms)\n")
    parts.append(f"## Diff\n\n```diff\n{diff}\n```\n")
    return "\n".join(parts)


def as_markdown(review, cost, model_id):
    """A pull request comment a person would be willing to read."""
    icon = {"block": "🛑", "warn": "⚠️", "approve": "✅"}[review.verdict]
    out = [f"### {icon} Terraform review — **{review.verdict}**", "",
           f"{review.headline}", ""]

    if review.findings:
        for f in sorted(review.findings,
                        key=lambda x: SEVERITY_ORDER.get(x.severity, 9)):
            out += [f"**`{f.address}`** · `{f.category}` · {f.severity}",
                    "", f"{f.explanation}", "",
                    f"<sub>{f.evidence}</sub>", ""]
    else:
        out += ["No findings.", ""]

    out.append(f"_{VERDICT_NOTE[review.verdict]}_")

    if review.suppressed:
        out += ["", "<details><summary>What I chose not to raise</summary>", "",
                review.suppressed, "", "</details>"]

    out += ["", "---",
            f"<sub>{len(review.findings)} finding(s) · ${cost:.4f} · "
            f"{model_id.split('.')[-1]} · reads the diff, not the plan · "
            f"advisory, does not block</sub>"]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".", help="repository to review")
    ap.add_argument("--base", default="main", help="base branch to diff against")
    ap.add_argument("--diff", help="read a diff from this file instead of git")
    ap.add_argument("--description", help="file holding the PR description")
    ap.add_argument("--max-diff-chars", type=int, default=MAX_DIFF_CHARS,
                    help="truncate diffs longer than this (0 disables)")
    ap.add_argument("--model", default="haiku", choices=list(M.MODELS))
    ap.add_argument("--profile", default=None, help="AWS profile to bill")
    ap.add_argument("--json", action="store_true", help="emit JSON, not markdown")
    ap.add_argument("--out", help="write the comment here as well as to stdout")
    args = ap.parse_args()
    M.use_profile(args.profile)

    diff = (pathlib.Path(args.diff).read_text(encoding="utf-8", errors="replace")
            if args.diff else terraform_diff(args.repo, args.base))
    if not diff.strip():
        print("No Terraform changes to review.", file=sys.stderr)
        return 0

    if args.max_diff_chars:
        capped = cap_diff(diff, args.max_diff_chars)
        if capped != diff:
            print(f"Diff is {len(diff)} characters; truncating to "
                  f"{args.max_diff_chars}.", file=sys.stderr)
            diff = capped

    description = (pathlib.Path(args.description).read_text(encoding="utf-8")
                   if args.description else None)

    review, response = M.call(build_prompt(diff, description), model=args.model)
    cost = M.usage_cost(response, args.model)

    if args.json:
        payload = M.to_findings_json(review)
        payload["cost_usd"] = round(cost, 5)
        print(json.dumps(payload, indent=2))
        return 0

    comment = as_markdown(review, cost, M.MODELS[args.model])
    print(comment)
    if args.out:
        pathlib.Path(args.out).write_text(comment, encoding="utf-8")
    # Advisory by construction: always exit 0, whatever the verdict.
    return 0


if __name__ == "__main__":
    sys.exit(main())
