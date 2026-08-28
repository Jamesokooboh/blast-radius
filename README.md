# Blast Radius

A Terraform pull request reviewer that reads the plan, not the diff — and earns
its place by throwing most of the scanner's output away.

**Status: complete.** Fifteen labelled cases, two scanner baselines, two model
baselines, six iterations, and a variance check that invalidated four of this
project's own findings. Full history in
[report/changelog.md](report/changelog.md), including every prediction that was
wrong.

**The result: nothing beat one prompt.** Three of the six agentic additions made
the review measurably worse, and the other three could not be distinguished from
doing nothing.

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

Built and measured:

- `infra/base/` — a 32-resource fixture stack (VPC, ALB, autoscaling group,
  RDS, three S3 buckets, IAM), no data sources
- `fixtures/base.tfstate` — the converged state fixture
- `plan.sh` — applies a case overlay, plans it, emits `plan.json` and the diff
- `score.py` — set-intersection scoring on (address, category), no LLM judge
- **all 15 cases**, labelled: 3 in band A, 4 in B, 6 in C, 2 in D, carrying
  10 real findings and 6 findings a good reviewer suppresses
- **both scanner baselines**, measured

Not built yet: the two model baselines (blocked only on an API key) and the
agent.

### Results

Primary metric is F1 over labelled findings. Every configuration marked (n=4) was
run four times; the spread matters more than any single number, and this project
learned that the hard way.

| configuration | F1 | | cost/PR |
| --- | --- | --- | --- |
| Raw Checkov — what CI runs today | 0.052 | 9.5 findings per PR | $0 |
| Checkov scoped to the change | 0.320 | the fair scanner baseline | $0 |
| **One prompt, Haiku 4.5 (n=4)** | **0.784 ± 0.078** | **the best thing measured** | **$0.007** |
| One prompt, Sonnet 4.6 | 0.783 | no better, 2× the price | $0.015 |
| + terraform plan (n=4) | 0.674 ± 0.038 | **worse** | $0.009 |
| + multi-agent split (n=4) | 0.653 ± 0.060 | **worse** | $0.026 |
| + tools and free exploration (n=4) | 0.588 ± 0.042 | **worst** | $0.133 |
| + scanner output as claims | 0.842 | no measurable effect | $0.007 |
| + citation verification | 0.900 | no measurable effect, free | $0.000 |
| + cost table | 0.842 | no measurable effect | $0.007 |
| + review memory | 0.800 | no measurable effect | $0.007 |

The scanner is far below everything a model does — the interesting comparison is
not against Checkov, it is between the simplest model configuration and the
elaborate ones. The elaborate ones lose.

Band C — the six cases built because a static scanner is structurally blind to
them — is where this is clearest. Checkov scores 0.14 there. One prompt with no
plan scores 0.86. Adding the plan drops it to 0.57.

### Gates

```
$ ./plan.sh --all            # every case produces its intended plan signal
--- case base ---   (no changes)
--- case 08 ---       delete/create  aws_db_instance.main
--- case 12 ---              update  aws_iam_role_policy.app_data
--- case 13 ---   (no changes)

$ python tools/make_oracle.py && python score.py --mode oracle
precision 1.000   recall 1.000   F1 1.000     # a perfect answer

$ python score.py --mode agent
precision 0.000   recall 0.000   F1 0.000     # nothing produced yet

$ python score.py --mode checkov-scoped       # day-two gate: F1 within 0.2 - 0.5
precision 0.308   recall 0.400   F1 0.348
```

`--mode oracle` is a harness self-test, not a measurement: `tools/make_oracle.py`
replays the labels back as findings to confirm the scorer awards a perfect score
to a perfect answer. Paired with an empty run scoring 0.000, it shows the scorer
discriminates in both directions rather than being pinned at one end.

Case 08 produces the `delete/create` on the production database the project
hangs on. Case 12 shows `aws_iam_role_policy.app_data` changing even though the
diff touches only `variables.tf` and the policy never appears in it. A perfect
answer scores 1.0 and an empty one scores 0.0, so the scorer discriminates in
both directions.

## Reproduction

Requires Terraform 1.9+ and Python 3.10+. Network is needed once, to fetch the
provider. No AWS account, no credentials, no cost.

```bash
pip install -r requirements.txt
./plan.sh --all                             # ~4 min, every plan and diff
python tools/run_checkov.py --all           # baseline A
python tools/run_checkov.py --all --scoped  # baseline A'
python score.py --mode checkov
python score.py --mode checkov-scoped
python tools/make_oracle.py
python score.py --mode oracle               # harness self-test, must be 1.000
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
tools/               make_state, fixture_ids, planfilter, emit_plan,
                     run_checkov, make_oracle
plan.sh              overlay -> plan.json + diff
score.py             findings x labels -> F1, band recall
results/             plans, diffs, findings, trajectories
```

A case's `overlay/` holds whole `.tf` files that replace their base version;
`plan.sh` copies base, applies the overlay, and diffs the two to produce the
pull request the reviewer would see.

### Scoring the scanner fairly

Checkov classifies by its own check ids, so scoring it against this project's
categories needs a mapping. That mapping lives in `tools/run_checkov.py` and is
published rather than buried, because it decides how well the baseline does.
Checks corresponding to a labelled category are mapped; everything else becomes
`hygiene` — a true observation about the stack that says nothing about this
pull request.

Nothing maps to `data-loss`, `guardrail`, `cost` or `reliability`, because
Checkov has no check for any of them. That absence is the finding, not an
oversight in the table.

Two scoring rules exist because the first version of each was wrong, and both
corrections lowered the score the agent will be able to claim:

- Findings match on address **and** category. An earlier address-only rule gave
  the scanner credit for naming the right resource for entirely unrelated
  reasons, inflating its band C recall from 0.14 to 0.43.
- `noise` labels match on **address alone**. Reporting that resource at all is
  the error, whatever category it is filed under. Matching noise on category too
  let a miscategorised parrot slip through, and reported 6 of 6 noise findings
  correctly suppressed when the true figure was 1 of 6.

## Disclosure

The fixture stack, the cases and the labels are all written for this project.
Labels are committed before any agent runs and each one cites the file line or
plan action that justifies it. Nothing here corresponds to real infrastructure;
the AWS account id in the fixtures is all zeros and the credentials in
`versions.tf` are the literal string `test`.
