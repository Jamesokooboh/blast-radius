# Video script — 5:00

Deliverable 3. Covers the required beats in order: the problem and the simple
baseline, one realistic execution end to end, the final comparison, the
changelog, the change that contributed most, and one experiment removed.

> **Read this first.** The live run below writes to `--mode demo`, not to
> `oneshot-haiku`. Running it without `--mode` overwrites the committed baseline
> result for case 08 and changes the numbers in the changelog. This happened once
> while checking the script; the file had to be restored from git.

**Before recording**, have these ready in separate terminal tabs so nothing is
typed live:

1. `cases/case-08-rds-encrypt-in-place/pr_description.md` open in an editor
2. `results/diffs/08.diff` open
3. A terminal in the repo root
4. `report/changelog.md` open at the results table

Timings are cumulative. Total spoken words ≈ 620, which leaves room for the
commands to run.

---

## 0:00 – 0:40 · The problem

> **On screen:** the case 08 pull request description.

"This is a pull request against production infrastructure. It says: enable
encryption at rest on the production database, to close a SOC 2 finding. One
line changes."

> **On screen:** switch to the diff. Highlight the single changed line.

```
-  storage_encrypted = false
+  storage_encrypted = true
```

"That's the whole change. It's a security improvement, it's correct, and every
reviewer I've shown it to approves it."

"Merging it destroys the database. `storage_encrypted` is immutable on RDS, so
Terraform satisfies that line by deleting the instance and creating a new empty
one. Nothing in the diff says so."

"The person who approves infrastructure pull requests is the last checkpoint
before production. This is the kind of thing they're there to catch."

---

## 0:40 – 1:10 · The simple baseline

> **On screen:** terminal.

```bash
python score.py --mode checkov-scoped
```

"The tool most teams already have is a static scanner. Here's Checkov, scored
against fifteen labelled pull requests — and scored generously: restricted to the
resources each change actually touches, which is better than what it does in CI."

> **On screen:** `precision 0.267  recall 0.400  F1 0.320`

"F1 of 0.32. On case 08 it does flag the database — for missing log exports. It
names the right resource for entirely the wrong reason, and it says nothing about
the deletion."

"Unscoped, in real CI, it reports nine and a half findings on every pull request
whatever changed. That's why nobody reads it."

---

## 1:10 – 2:20 · One realistic execution

> **On screen:** terminal, run it live.

```bash
python tools/run_oneshot.py --case 08 --model haiku --mode demo
```

"So here's the agent. One prompt: the diff, the pull request description,
instructions to report at most five findings and to say nothing about things that
don't matter. Claude Haiku 4.5, through Bedrock. No plan, no tools, no retries."

> **On screen:** the run completes in about ten seconds, for well under a cent.

```
case 08: block   ...  ~10s  ~$0.007
```

"Verdict: block."

> **On screen:** open the committed result,
> `results/findings/oneshot-haiku/08.json`, and find the finding on
> `aws_db_instance.main`.

"The finding is on the database, and it's categorised `data-loss`:"

> **Read the finding aloud:**

"*The `storage_encrypted` attribute is immutable after creation. Terraform will
destroy the current database and create a new empty one.*"

> The exact wording varies between runs — read whatever the committed file says.
> The category is the part that matters, and it is `data-loss` in every baseline
> run.

"Six tenths of a cent, ten seconds. It got there from the diff alone — it knew
that attribute is immutable without being shown the plan."

---

## 2:20 – 3:05 · The experiment we removed

"Which brings me to the thing this project was built around, and cut."

"The premise was that a reviewer needs the `terraform plan`, because the diff
doesn't say what will happen. So iteration one adds the plan — same model, same
prompt, same code path, one flag."

> **On screen:** open `results/findings/i1plan-haiku/08.json` side by side with the
> previous one.

"Same case. Still blocks it. Still the right resource. But look at the category."

> **Highlight:** `reliability`, not `data-loss`.

> **Read aloud:**

"*The production database will be destroyed and recreated. The application will
lose connectivity during the recreation, which can take ten to thirty minutes.*"

"Downtime. Not data loss. Shown a plan that says `delete` then `create`, it
reasoned about the resource lifecycle and stopped reasoning about what was inside
it. The plan is more accurate than the diff, and it made the review worse."

"Across all fifteen cases: 0.78 without the plan, 0.67 with it. We removed it."

---

## 3:05 – 4:05 · The change that contributed most

"The change that contributed most to this project didn't improve the agent at
all. It's this."

> **On screen:** terminal.

```bash
for m in oneshot-haiku oneshot-haiku-r2 oneshot-haiku-r3 oneshot-haiku-r4; do
  python score.py --mode $m | grep ^precision
done
```

> **On screen:** four different F1 values — 0.900, 0.737, 0.762, 0.737.

"That's the same configuration, run four times, unchanged. 0.90, 0.74, 0.76,
0.74."

"For most of this project I reported 0.90 — and 0.90 was the best of four. I'd
already written up four separate iterations as regressions against it, each with
a plausible mechanism, each committed."

"Three of those four evaporated. They were inside the noise. The best story I
had — that giving the agent a cost table made it stop reporting cost — died here:
one baseline run dropped that finding too, without any cost table."

"Twelve minutes and thirty-three cents. It should have been the second
measurement in the project, not the twenty-second."

---

## 4:05 – 5:00 · Final comparison and the hot take

> **On screen:** the results table from `report/changelog.md`.

"So here's everything, with the three regressions re-run four times each so
they're compared distribution against distribution."

| | F1 | $/PR |
| --- | --- | --- |
| Checkov, scoped | 0.320 | $0 |
| **One prompt** | **0.784 ± 0.078** | **$0.007** |
| + terraform plan | 0.674 | $0.009 |
| + multi-agent split | 0.653 | $0.026 |
| + tools and free exploration | 0.588 | $0.133 |

"Nothing beat one prompt. Three additions made it measurably worse, and the other
three couldn't be distinguished from doing nothing."

"The worst was the most capable thing I built — an agent with tools, the plan,
the scanner and unlimited steps. Nineteen times the cost, and it wandered:
reviewing a load balancer change, it reported a finding about the database,
because it could read the whole directory and did."

"Two things I'd take to the next project."

"Every context you add to fix a blind spot also tells the model that blind spot
is someone else's job now. The plan made the review about resource lifecycles.
The scanner made it about security. The cost table made the money look already
accounted for."

"And a single run is not a measurement. My pipeline had structured outputs, fixed
prompts, deterministic scoring — everything downstream of the model was
reproducible, which quietly convinced me the model was too. Measure your noise
floor before you measure anything else, and refuse to interpret any difference
smaller than it."

> **On screen:** the repo URL.

"Everything's reproducible — fifteen labelled cases, twenty-four configurations,
about ten dollars end to end. The four-minute version is in the README."

---

## Notes for the edit

- The single most valuable shot is the two case 08 findings side by side, with
  `data-loss` and `reliability` visible at the same time. Hold it.
- The four variance numbers should appear one at a time if the edit allows it.
  The beat lands on the fourth.
- Do not smooth over the retraction. A project that withdrew four of its own
  findings is more credible than one that reported eight.
- Model output is not deterministic. The live run will not match the committed
  file word for word, and may return a different number of findings. Narrate the
  verdict and the category, never an exact count. If a take produces something
  that contradicts the committed result, say so on camera rather than re-shooting
  until it agrees — that is the whole point of the variance section.
- If it runs long, cut the Checkov section to a single sentence over the score.
  Everything else is load-bearing.
