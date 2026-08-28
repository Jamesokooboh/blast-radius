# Improvement Changelog

Predictions were written before each stage ran and are kept visible next to the
measurement, including where they were wrong.

Primary metric: **F1 over labelled findings**, matched by (resource address,
category) across 15 pull requests carrying 10 real findings and 6 findings a
good reviewer suppresses. Scoring is set intersection — no model grades another
model anywhere in this project.

| Stage | What ran, and why | Predicted | Measured | Decision |
| --- | --- | --- | --- | --- |
| **B0** | Raw Checkov, exactly as CI runs it today: whole-stack static scan, no plan, no PR description. The status quo. | F1 0.35 | **F1 0.053** — precision 0.028, recall 0.400, **9.5 findings per PR** | Keep as the honest status-quo number |
| **B0′** | Checkov scoped to the resources the plan actually changes, as a competent CI integration would. A deliberately *stronger* baseline. | — | **F1 0.320** — precision 0.267, recall 0.400, **0.9 findings per PR** | Keep as the scanner baseline |
| **B1** | One direct prompt over the diff and PR description. Sonnet 4.6, no plan, no scanner, no tools. | F1 0.45 | **F1 0.783** — precision 0.692, recall 0.900, band C recall 0.86 | Keep. Prediction badly wrong; see below |
| **B1′** | The same prompt on Haiku 4.5, to test whether the result is about the task or the model. | worse than B1 | **F1 0.900** — precision 0.900, recall 0.900, noise 7 of 7 suppressed | **The new bar.** The cheap model won |
| B2 | General agent with shell access, no task structure. | F1 0.55 | not yet run | — |

## Stage notes

### B0 — the status quo is worse than predicted, in the way that matters

F1 0.053 against a predicted 0.35. The miss is entirely precision: 0.028. Recall
was as expected at 0.400.

The reason is the thing the project exists to fix. Checkov reports on the whole
stack on every run, so each of the 15 pull requests draws the same ~9.5 flagged
resources regardless of what the change touched. Recall is unaffected, precision
collapses, and the practical result is the one every team recognises — a CI
check that is red on every pull request and therefore read on none.

Recording this as a failed prediction rather than adjusting the target: the
0.35 estimate was made thinking of Checkov's accuracy on the resources it
examines, not of its output volume per pull request. Those are different
quantities and only the second one reaches a reviewer.

### B0′ — building the strongest fair version of the baseline

Comparing an agent against an unreadable wall of output would be a strawman, so
the baseline was strengthened rather than left where it fell. Restricting
Checkov to the resources the plan changes is what a diff-aware CI integration
does, and it is a much harder thing to beat: findings per pull request fall from
9.5 to 0.9 and F1 rises from 0.053 to 0.348.

**B0′ is the number the agent has to beat.** B0 is reported alongside it because
it is what the user actually experiences today.

### B1 — the prediction was wrong by enough to change the project

Predicted F1 0.45. Measured **0.783**, against the scanner's 0.320. The
pre-registered target for the *finished agent* was 0.80, and a single prompt
over the diff essentially reaches it.

The number that matters is band C. Those six cases exist because a static
scanner is structurally blind to them — cross-file effects, plan transitions,
cost, a removed guardrail — and Checkov scores 0.14 there. A one-shot prompt
scores **0.86**. Reading the findings shows why: the model knew from the diff
alone that `storage_encrypted` is immutable on `aws_db_instance` and forces
replacement, that `desired_capacity = 1` under `min_size = 3` will be reverted
by the autoscaling service, that a second NAT gateway costs real money, and that
removing `prevent_destroy` matters even though the plan shows nothing.

**This substantially disproves the I1 hypothesis.** The premise of iteration I1
was that an agent needs `plan.json` to see what the diff hides. It turns out a
capable model infers most of those transitions without it. Structurally blind to
a *scanner* is not the same property as hard for a *model*, and the case set was
designed around the first while the metric measures the second.

What remains is more interesting than what was lost. The headroom is no longer
recall (0.900 — the baseline finds nearly everything) but **precision (0.692)
and verdict accuracy (0.733)**. B1 reprints 3 of 7 findings a good reviewer
suppresses: it flags plain HTTP on a listener that never leaves the VPC, and a
staging bucket whose contents expire in a day. The remaining work is judgment
and restraint, not detection.

The project's question therefore changes from *can an agent beat a linter* —
answered, trivially, by one prompt — to **does agent machinery add anything over
a competent one-shot reviewer?** That is a harder question and a more honest one,
and "mostly no" is a publishable answer.

Consequences for the remaining stages, decided now rather than after seeing
which way the numbers fall:

- I1 (plan JSON) is now expected to add little. It runs anyway, because a
  measured null result on the project's own central hypothesis is worth more
  than a quietly dropped stage.
- I2 (linter output as evidence to adjudicate) and I3 (citation verification)
  target precision, which is where the headroom actually is. They are promoted
  ahead of I1 in importance.
- The pre-registered target of F1 0.80 is retained rather than raised. Moving a
  target after seeing the baseline is how a project talks itself into a result.

### B1′ — the cheaper model beat the more expensive one, and the reason is restraint

Run to answer a narrow question: is B1's 0.783 a fact about the task or about
Sonnet 4.6? The prediction was that Haiku 4.5, at a third of the price, would do
noticeably worse on the judgment-heavy cases.

It did better. **F1 0.900 against 0.783**, at $0.11 for the full fifteen cases
versus $0.22, and faster per case.

Where the two models are identical:

| | Sonnet 4.6 | Haiku 4.5 |
| --- | --- | --- |
| recall | 0.900 | 0.900 |
| band C recall | 0.86 | 0.86 |
| band A recall | 1.00 | 1.00 |
| false blocks on clean PRs | 0 | 0 |

They find the same things. Detection is not what separates them.

Where they differ, in opposite directions:

| | Sonnet 4.6 | Haiku 4.5 |
| --- | --- | --- |
| precision | 0.692 | **0.900** |
| noise correctly suppressed | 4 of 7 | **7 of 7** |
| verdict accuracy | **0.733** | 0.667 |
| findings per PR | 0.9 | 0.7 |

Sonnet reprints three findings a good reviewer suppresses — plain HTTP on a
listener that never leaves the VPC, an internal load balancer sharing a security
group, a staging bucket whose contents expire in a day. Haiku suppresses all
seven and says nothing about any of them.

Haiku's failure is the mirror image. On cases 01, 02, 03, 09 and 10 it finds the
right problem and then files it as `warn` where the label says `block`. It calls
an unrestricted `Action: "*"` administrative policy a warning. It finds the
right thing and under-calls it.

So neither model is better at reviewing. One over-reports and escalates
correctly; the other under-reports nothing and under-escalates everything. Both
failure modes are calibration, and both look addressable by prompt and
verification rather than by model capability — which is the strongest evidence
so far for where the remaining work actually is.

**B1′ becomes the bar the agent has to beat**, on the same principle that made
scoped Checkov the baseline rather than raw Checkov: compare against the
strongest fair version of the alternative. That means the agent now has to beat
F1 0.900 at $0.007 per pull request, which is a far harder target than the 0.320
it started with and than the 0.80 that was pre-registered. The pre-registered
target is left where it is; the bar is what moved.

### A case in the set contained a real finding, and B1 found it

Case 05 tests whether the agent suppresses scanner noise about an internal load
balancer. The original overlay added `aws_lb.internal` with no listener and no
target group — which is a genuine reliability defect, since a load balancer with
no listener routes nothing. B1 reported it and was scored as a false positive
for being correct.

A case meant to measure suppression cannot contain a real problem. The overlay
now includes the target group and listener that make the change complete, and
the case was re-planned, re-scanned and re-run. Scoped Checkov moved 0.348 →
0.320 and B1 0.818 → 0.783 as a result; both are reported at the corrected
values throughout.

This is the second defect found by reading outputs rather than scores, and the
second correction that made the agent's job harder rather than easier.

### The scoring methodology was wrong three times

Recorded because all three were caught by looking at outputs rather than scores,
and every fix raised a baseline rather than the agent.

1. **Address-only matching gave the scanner free recall.** Scoring the baseline
   generously — credit for naming the right resource, however it classified the
   problem — put Band C recall at 0.43. Inspecting it showed why: Checkov flags
   `aws_s3_bucket.data` on every single case for cross-region replication, event
   notifications and KMS encryption, and case 15's finding happens to sit on that
   same resource. It was being credited for naming the right resource for
   entirely unrelated reasons. Replaced with a published check-id → category map
   (`tools/run_checkov.py`), under which Band C recall falls to 0.14.

2. **An input variable has three legitimate names and only one was accepted.**
   Sonnet wrote `variable.app_data_bucket_arns`, Haiku wrote
   `var.app_data_bucket_arns`, and the label carried the bare name — so case 12
   scored zero for both while both had found exactly the right thing. Which form
   a reviewer picks says nothing about review quality, so `norm()` now strips the
   `var.` and `variable.` prefixes. This raised Haiku from 0.800 to 0.900 and had
   already raised Sonnet from 0.727 to 0.818.

3. **Noise labels were matched by address *and* category, so miscategorising a
   noise finding laundered it.** Checkov reports the case 06 public-bucket
   resources as `network-exposure` while the label carries category `noise`, so
   the keys never met and the harness reported 6/6 noise correctly suppressed
   when the true figure was 1/6. Noise now matches on address alone: raising that
   resource at all is the error, whatever it is filed under.

### One prediction about the case set was wrong

Case 12 widens an IAM policy by editing a variable default three files away; the
policy resource never appears in the diff. It was labelled `linter_catches:
false` on the assumption that a static scanner would not resolve the variable.

**Checkov resolves it** and fires `CKV_AWS_355` on
`aws_iam_role_policy.app_data`. It is the only Band C case the scanner finds,
and it is the whole of Checkov's 0.14 Band C recall. The label has been
corrected to `linter_catches: true` and the case kept in Band C, since what it
tests — reasoning about an effect absent from the diff — is still what separates
it from Band A for the diff-reading baselines.

## Every stage measured so far

| | Raw Checkov | Scoped Checkov | B1 Sonnet 4.6 | B1′ Haiku 4.5 |
| --- | --- | --- | --- | --- |
| **F1** | 0.052 | 0.320 | 0.783 | **0.900** |
| precision | 0.028 | 0.267 | 0.692 | 0.900 |
| recall | 0.400 | 0.400 | 0.900 | 0.900 |
| verdict accuracy | 0.467 | 0.467 | **0.733** | 0.667 |
| band A recall | 1.00 | 1.00 | 1.00 | 1.00 |
| band C recall | 0.14 | 0.14 | 0.86 | 0.86 |
| noise suppressed | 1 of 7 | 1 of 7 | 4 of 7 | **7 of 7** |
| false blocks (band D) | 1 | 1 | 0 | 0 |
| findings per PR | 9.5 | 0.9 | 0.9 | 0.7 |
| cost per PR | $0 | $0 | $0.015 | $0.007 |

Band C is the project's reason for existing. The scanner scores 0.14 there; both
models score 0.86 from the diff alone. The gap between the scanner and a single
prompt is enormous; the gap between a single prompt and anything more elaborate
is what remains to be shown.

## Model access: what actually runs, and why

Runs go through **Amazon Bedrock** on AWS account 313951301623, authenticated by
the ordinary AWS credential chain, so no API key exists anywhere in this
repository. Reproducing this needs an AWS account with Anthropic model access,
not an Anthropic API key.

Three things cost time here and are recorded so nobody repeats them:

1. **Bedrock serves newer Claude models through inference profiles.** The id
   must carry a `us.` prefix and go through the `bedrock-runtime` InvokeModel
   path (`AnthropicBedrock`), not the Messages/Mantle endpoint
   (`AnthropicBedrockMantle`). Measured on this account:

   | id | result |
   | --- | --- |
   | `anthropic.claude-sonnet-5` | 403 on Mantle |
   | `us.anthropic.claude-sonnet-5` | 404 on Mantle, AccessDenied on InvokeModel |
   | `us.anthropic.claude-sonnet-4-6` | works |

2. **`ListFoundationModels` returns ids for the wrong endpoint.** It lists dated
   forms like `anthropic.claude-haiku-4-5-20251001-v1`, which 404 on the
   Messages endpoint. Copying ids from that listing makes things worse.

3. **The Claude 5 family is not available on either account tested.** Sonnet 5,
   Opus 5, Fable 5, Opus 4.7 and Opus 4.8 all return AccessDenied; 4.6 and 4.5
   are granted. The Bedrock console's "Model access" page has been retired and
   its replacement auto-enables on first invocation, so there is no form to fill
   in -- the denial is account eligibility, not a missing opt-in.

So the reported runs use **Claude Sonnet 4.6** (`us.anthropic.claude-sonnet-4-6`,
$3/$15 per MTok) and the cheap comparison runs use **Claude Haiku 4.5**
(`us.anthropic.claude-haiku-4-5-20251001-v1:0`, $1/$5). Opus 4.6 is available and
deliberately unused: two models answer "does the cheaper one hold up", and a
third only adds spend.

Verified on this path: adaptive thinking, `output_config.effort`, and structured
outputs all work on Sonnet 4.6. Haiku 4.5 rejects `effort` and takes
`thinking: {type: "enabled", budget_tokens: N}` instead, which `tools/model.py`
handles.

## Still to run

B2, the general agent with shell access.
