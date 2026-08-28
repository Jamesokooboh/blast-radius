#!/usr/bin/env python3
"""Baseline B2: a general agent with tools and no task-specific structure.

This is the honest agentic floor. It gets strictly more than B1 -- the whole case
working directory, which holds the Terraform files, the human-readable
`plan.txt`, the raw plan JSON and the state -- plus the ability to run the
scanner. It decides for itself what to look at and when to stop.

What it deliberately does NOT have is the structure the agent stages add: no
pre-digested plan, no framing of scanner output as claims to adjudicate, no
citation verification, no attempt budget shaped around the task. Just capability.

Tool surface is confined on purpose. The model cannot author shell commands: it
can list and read files inside one case directory, and it can run checkov with
fixed arguments. Nothing it emits is executed. That is a deliberate deviation
from "give the agent a shell", made because this runs on a workstation with live
cloud credentials, and it is recorded in the changelog rather than glossed.

    python tools/run_agent_b2.py --case 08
    python tools/run_agent_b2.py --all
"""

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import model as M  # noqa: E402

ROOT = M.ROOT
MAX_STEPS = 14
MAX_READ = 60_000

TOOLS = [
    {
        "name": "list_files",
        "description": "List the files in the working directory for this pull request.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "read_file",
        "description": (
            "Read a file from the working directory. Terraform sources are the .tf "
            "files; plan.txt is the human-readable terraform plan; plan.raw.json is "
            "the same plan as JSON; terraform.tfstate is the prior state."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "File name"}},
            "required": ["name"],
        },
    },
    {
        "name": "run_checkov",
        "description": "Run the checkov static scanner over the Terraform in this directory.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "submit_review",
        "description": "Submit the finished review. Call this exactly once, when done.",
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["block", "warn", "approve"]},
                "headline": {"type": "string"},
                "suppressed": {"type": "string"},
                "findings": {
                    "type": "array",
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "properties": {
                            "address": {"type": "string"},
                            "category": {"type": "string", "enum": list(M.CATEGORIES)},
                            "severity": {"type": "string",
                                         "enum": ["critical", "high", "medium", "low"]},
                            "evidence": {"type": "string"},
                            "explanation": {"type": "string"},
                        },
                        "required": ["address", "category", "severity",
                                     "evidence", "explanation"],
                    },
                },
            },
            "required": ["verdict", "headline", "findings"],
        },
    },
]


def workdir(cid):
    d = ROOT / ".work" / cid
    if not d.exists():
        sys.exit(f"{d} missing -- run ./plan.sh {cid} first")
    return d


def run_tool(name, args, wd):
    """Execute one tool. Nothing the model writes reaches a shell."""
    if name == "list_files":
        return "\n".join(sorted(f.name for f in wd.iterdir() if f.is_file()))

    if name == "read_file":
        target = (wd / pathlib.Path(args.get("name", "")).name).resolve()
        if target.parent != wd.resolve() or not target.is_file():
            return f"No such file: {args.get('name')!r}"
        text = target.read_text(encoding="utf-8", errors="replace")
        if len(text) > MAX_READ:
            return text[:MAX_READ] + f"\n\n[truncated at {MAX_READ} of {len(text)} chars]"
        return text

    if name == "run_checkov":
        exe = shutil.which("checkov")
        if not exe:
            return "checkov is not installed"
        with tempfile.TemporaryDirectory() as tmp:
            scan = pathlib.Path(tmp) / "tf"
            scan.mkdir()
            for f in wd.glob("*.tf"):
                shutil.copy2(f, scan / f.name)
            r = subprocess.run([exe, "-d", str(scan), "--framework", "terraform",
                                "--compact", "--quiet"], capture_output=True, text=True)
        out = r.stdout or r.stderr
        return out[:MAX_READ] if out.strip() else "checkov reported nothing"

    return f"unknown tool {name}"


def review_one(cid, model_key, effort):
    wd = workdir(cid)
    pr = (list(ROOT.glob(f"cases/case-{cid}-*"))[0] / "pr_description.md").read_text(encoding="utf-8")

    system = M.review_instructions() + (
        "\n\n## How to work\n\n"
        "You have tools for listing and reading the files in this pull request's "
        "working directory, and for running a static scanner over it. Investigate "
        "however you see fit, then call `submit_review` exactly once with your "
        "conclusions. Nothing you write is executed."
    )
    messages = [{"role": "user", "content":
                 f"Review this Terraform pull request.\n\n"
                 f"## Pull request description\n\n{pr}\n\n"
                 f"The working directory holds the Terraform after the change, "
                 f"the plan, and the prior state. Start by listing the files."}]

    client = M.client()
    trace, cost, submitted = [], 0.0, None

    for step in range(MAX_STEPS):
        kwargs = dict(model=M.MODELS[model_key], max_tokens=8000,
                      system=system, messages=messages, tools=TOOLS)
        if model_key in M.LEGACY_THINKING:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 2048}
        else:
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": effort}

        resp = client.messages.create(**kwargs)
        cost += M.usage_cost(resp, model_key)
        messages.append({"role": "assistant", "content": resp.content})

        calls = [b for b in resp.content if b.type == "tool_use"]
        if not calls:
            # No tool call and no submission: nudge once, then give up.
            messages.append({"role": "user", "content":
                             "Call submit_review with your conclusions."})
            trace.append({"step": step, "note": "no tool call; nudged"})
            continue

        results = []
        for call in calls:
            if call.name == "submit_review":
                submitted = call.input
                results.append({"type": "tool_result", "tool_use_id": call.id,
                                "content": "Review recorded."})
                trace.append({"step": step, "tool": call.name, "input": call.input})
            else:
                out = run_tool(call.name, call.input or {}, wd)
                results.append({"type": "tool_result", "tool_use_id": call.id,
                                "content": out})
                trace.append({"step": step, "tool": call.name,
                              "input": call.input, "result_chars": len(out)})
        messages.append({"role": "user", "content": results})

        if submitted is not None:
            break

    return submitted, trace, cost, step + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--model", default="haiku", choices=list(M.MODELS),
                    help="haiku by default: B1' on haiku is the bar to beat")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--force", action="store_true",
                    help="redo cases that already have output; default is to resume")
    ap.add_argument("--mode", default=None,
                    help="output directory name; for repeat runs")
    args = ap.parse_args()
    M.use_profile(args.profile)

    mode = args.mode or f"agent-b2-{args.model}"
    out = ROOT / "results" / "findings" / mode
    traj = ROOT / "results" / "trajectories" / mode
    out.mkdir(parents=True, exist_ok=True)
    traj.mkdir(parents=True, exist_ok=True)

    ids = (sorted(d.name.split("-")[1] for d in ROOT.glob("cases/case-*"))
           if args.all else [args.case])
    if not ids or ids == [None]:
        sys.exit("pass --case NN or --all")

    who = M.whoami()
    print(f"  billing: profile {who['profile']}  account {who['account']}  "
          f"model {M.MODELS[args.model]}\n")

    if not args.force:
        done = {p.stem for p in out.glob("*.json")}
        skipped = [c for c in ids if c in done]
        ids = [c for c in ids if c not in done]
        if skipped:
            print(f"  resuming: {len(skipped)} case(s) already done, "
                  f"{len(ids)} to run\n")
        if not ids:
            print("  nothing to do; pass --force to redo")
            return

    total_cost, total_steps = 0.0, 0
    for n, cid in enumerate(ids):
        if n:
            time.sleep(5)   # Bedrock throttles multi-step loops; be a good citizen
        t0 = time.time()
        submitted, trace, cost, steps = review_one(cid, args.model, args.effort)
        elapsed = time.time() - t0
        total_cost += cost
        total_steps += steps

        payload = {"verdict": None, "headline": "", "findings": []}
        if submitted:
            payload = {
                "verdict": submitted.get("verdict"),
                "headline": submitted.get("headline", ""),
                "suppressed": submitted.get("suppressed"),
                "findings": [
                    {"address": f.get("address", ""), "category": f.get("category", ""),
                     "severity": f.get("severity", ""),
                     "evidence_ref": f.get("evidence", ""),
                     "explanation": f.get("explanation", "")}
                    for f in (submitted.get("findings") or [])
                ],
            }
        (out / f"{cid}.json").write_text(json.dumps(payload, indent=2))
        (traj / f"{cid}.json").write_text(json.dumps({
            "case": cid, "stage": "B2 general agent with tools",
            "model": M.MODELS[args.model], "aws_account": who["account"],
            "steps": steps, "tool_calls": trace, "response": payload,
            "elapsed_s": round(elapsed, 1), "cost_usd": round(cost, 4),
        }, indent=2))

        tools_used = [t.get("tool") for t in trace if t.get("tool")]
        print(f"  case {cid}: {str(payload['verdict']):<8} "
              f"{len(payload['findings'])} finding(s)  {steps:>2} steps  "
              f"{elapsed:5.1f}s  ${cost:.4f}  [{','.join(tools_used[:6])}]")

    print(f"\n  {len(ids)} case(s), {total_steps} steps, ${total_cost:.2f}")
    print(f"  -> score with: python score.py --mode {mode}")


if __name__ == "__main__":
    main()
