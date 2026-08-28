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
| **B0′** | Checkov scoped to the resources the plan actually changes, as a competent CI integration would. A deliberately *stronger* baseline. | — | **F1 0.348** — precision 0.308, recall 0.400, **0.9 findings per PR** | Keep as the headline baseline |
| B1 | One direct prompt over the diff and PR description. | F1 0.45 | not yet run | blocked on an API key |
| B2 | General agent with shell access, no task structure. | F1 0.55 | not yet run | blocked on an API key |

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

### The scoring methodology was wrong twice, and both fixes lowered the agent's future score

Recorded because both were caught by looking at the baseline's output rather
than at its score.

1. **Address-only matching gave the scanner free recall.** Scoring the baseline
   generously — credit for naming the right resource, however it classified the
   problem — put Band C recall at 0.43. Inspecting it showed why: Checkov flags
   `aws_s3_bucket.data` on every single case for cross-region replication, event
   notifications and KMS encryption, and case 15's finding happens to sit on that
   same resource. It was being credited for naming the right resource for
   entirely unrelated reasons. Replaced with a published check-id → category map
   (`tools/run_checkov.py`), under which Band C recall falls to 0.14.

2. **Noise labels were matched by address *and* category, so miscategorising a
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

## Band recall, both baselines

| Band | What it holds | Raw Checkov | Scoped Checkov |
| --- | --- | --- | --- |
| A — real problems the scanner catches | 3 cases | 1.00 | 1.00 |
| B — correct but irrelevant findings | 4 cases | suppressed 1 of 6 | suppressed 1 of 6 |
| C — cross-file, plan-transition, cost | 6 cases, 7 findings | 0.14 | 0.14 |
| D — genuinely clean pull requests | 2 cases | 1 false block | 1 false block |

Band C is the project's reason for existing and the scanner scores 0.14 there,
finding one case out of seven labelled findings. Band D shows the other half of
the problem: Checkov blocks case 14, a pull request that adds two tags.

## Still to run

B1 and B2 need `ANTHROPIC_API_KEY`. Nothing about the harness blocks them.
