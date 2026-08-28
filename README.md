# Blast Radius

A Terraform pull request reviewer that reads the plan, not the diff — and earns
its place by throwing most of the scanner's output away.

**Status: day one of five.** The evaluation harness is built and both halves of
its gate pass. The agent itself is not written yet. See
[Current state](#current-state) for exactly what runs today.

---

## The problem

The user is whoever approves infrastructure pull requests on a small team —
usually one or two people who own production and review Terraform written by
everyone else.

The diff does not tell you what will happen. A three-line change can replace a
database. A variable default edited in one file can widen an IAM policy defined
in another. Meanwhile the scanner in CI emits forty findings per pull request,
most of them correct and irrelevant, so the team learned months ago to scroll
past it. The tooling is simultaneously too noisy to read and too shallow to
catch the things that cause incidents.

This is the last human checkpoint before a change reaches production. The cost
of missing something is downtime or a data-loss postmortem. The cost of the
noise is that nobody reads the checkpoint at all.

## The design constraint that shapes everything

The obvious version of this project scores itself against Checkov or tfsec
labels — and that version is dead on arrival, because then running Checkov
scores a perfect 1.0 and the agent is an expensive wrapper.

So the case set is built so that a static scanner *structurally cannot* win.
Cases are grouped into four bands:

| Band | What it contains | The scanner |
| --- | --- | --- |
| A | Real problems the scanner catches | catches — the agent must not regress |
| B | Correct-but-irrelevant findings | false positives — suppression is the skill |
| C | Cross-file, plan-transition and cost problems | structurally blind |
| D | Genuinely clean pull requests | — does the agent invent problems? |

A label with category `noise` is a finding a good reviewer suppresses.
Reporting one costs precision. That is what stops the agent from scoring well by
reprinting the scanner.

## Two things worth knowing about the harness

**No AWS account is needed.** The provider is configured with dummy credentials
and every call that would reach the API is disabled, so `terraform plan` runs
offline. The cost of a full run is the model tokens and nothing else. The
constraint this imposes: no data sources anywhere in the fixture stack, since
those do hit the API. Anything that would normally be looked up is a variable.

**Prior state is synthesized, not applied.** `terraform plan` against an empty
state reports every resource as `create`, so a *replace* or a *destroy* cannot
occur — and those are exactly the transitions a scanner cannot see. Rather than
standing up LocalStack, `tools/make_state.py` derives state from the plan's own
`planned_values`, fills the identifiers that are only known after apply, and
then converges: write state, re-plan, fold the result back in, repeat until the
plan is a clean no-op. It converges in four rounds. Run once; the result is
committed as `fixtures/base.tfstate` and judges never run it.

One consequence, documented because it is a real limitation:
`aws_db_instance` always reports an in-place update against synthesized state,
even when every attribute before and after is identical. `tools/planfilter.py`
drops updates whose `before` equals `after`. The rule is narrow and provable —
an update that changes nothing is not a change — and it cannot hide a real
finding, including the replace in case 08, which does change an attribute.

## Current state

Built and passing:

- `infra/base/` — a 32-resource fixture stack (VPC, ALB, autoscaling group,
  RDS, three S3 buckets, IAM), no data sources
- `fixtures/base.tfstate` — the converged state fixture
- `plan.sh` — applies a case overlay, plans it, emits `plan.json` and the diff
- `score.py` — set-intersection scoring on (address, category), no LLM judge
- three cases: `01` (band A), `08` (band C), `13` (band D)

Not built yet: the remaining twelve cases, the three baselines, and the agent.

**Day-one gate, both halves passing:**

```
$ ./plan.sh --all
--- case base ---   (no changes)
--- case 01 ---              update  aws_security_group.app
--- case 08 ---       delete/create  aws_db_instance.main
--- case 13 ---   (no changes)

$ python score.py --mode oracle   # hand-written perfect answers
precision 1.000   recall 1.000   F1 1.000

$ python score.py --mode agent    # nothing written yet
precision 0.000   recall 0.000   F1 0.000
```

The base stack is a clean no-op, case 08 produces the `delete/create` on the
production database that the whole project hangs on, and case 13's `moved`
blocks resolve to a pure state move. A perfect answer scores 1.0 and an empty
one scores 0.0, so the scorer discriminates in both directions.

## Reproduction

Requires Terraform 1.9+ and Python 3.10+. Network is needed once, to fetch the
provider. No AWS account, no credentials, no cost.

```bash
pip install -r requirements.txt
./plan.sh --all
python score.py --mode oracle
```

To regenerate the state fixture from scratch (not normally needed):

```bash
python tools/make_state.py --dir infra/base --out fixtures/base.tfstate
```

Self-checks:

```bash
python tools/planfilter.py    # phantom-change filter
python score.py --selfcheck   # scoring logic
```

## Layout

```
infra/base/          fixture stack, 32 resources
fixtures/            the converged state fixture
cases/case-NN-*/     overlay/ (the pull request), pr_description.md, labels.yaml
tools/               make_state, fixture_ids, planfilter, emit_plan
plan.sh              overlay -> plan.json + diff
score.py             findings x labels -> F1, band recall
results/             plans, diffs, findings, trajectories
```

A case's `overlay/` holds whole `.tf` files that replace their base version;
`plan.sh` copies base, applies the overlay, and diffs the two to produce the
pull request the reviewer would see.

## Disclosure

The fixture stack, the cases and the labels are all written for this project.
Labels are committed before any agent runs and each one cites the file line or
plan action that justifies it. Nothing here corresponds to real infrastructure;
the AWS account id in the fixtures is all zeros and the credentials in
`versions.tf` are the literal string `test`.
