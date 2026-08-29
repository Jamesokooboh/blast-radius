#!/usr/bin/env bash
# Records the 5-minute walkthrough as a single silent terminal take.
#
# Start your screen recorder, run this, stop the recorder. Every beat holds long
# enough for the matching narration in report/video-script.md, with a few seconds
# of slack for trimming. Then lay the voice over it in CapCut.
#
#   ./demo.sh              # real timing, ~5 minutes
#   SPEED=8 ./demo.sh      # 8x faster, to rehearse without recording
#
# Writes only to --mode demo. It cannot touch the committed results.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SPEED="${SPEED:-1}"
hold() { sleep "$(python -c "print($1/$SPEED)")"; }

banner() {
  printf '\n\033[1;34m%s\033[0m\n' "────────────────────────────────────────────────────────────"
  printf '\033[1;34m  %s\033[0m\n' "$1"
  printf '\033[1;34m%s\033[0m\n\n' "────────────────────────────────────────────────────────────"
}

clear

# ── 0:00 the problem ────────────────────────────────────────────────────────
banner "A pull request against production infrastructure"
cat cases/case-08-rds-encrypt-in-place/pr_description.md
hold 20

banner "The entire change"
grep -E '^[-+]' results/diffs/08.diff | grep -vE '^(\+\+\+|---)' | grep storage_encrypted
hold 20

# ── 0:40 the simple baseline ────────────────────────────────────────────────
banner "The baseline: a static scanner, scored generously"
python score.py --mode checkov-scoped | tail -5
hold 16

banner "What the scanner says about case 08"
python -c "
import json,pathlib
d=json.loads(pathlib.Path('results/findings/checkov-scoped/08.json').read_text())
f=d['findings'][0]
print(f\"  {f['address']}  [{f['category']}]\")
print(f\"  {f['evidence_ref']}\")"
hold 18

# ── 1:10 one realistic execution ────────────────────────────────────────────
banner "The agent: one prompt, the diff, Haiku 4.5 on Bedrock"
python tools/run_oneshot.py --case 08 --model haiku --mode demo
hold 12

banner "The finding"
python -c "
import json,pathlib
d=json.loads(pathlib.Path('results/findings/oneshot-haiku/08.json').read_text())
f=d['findings'][0]
print(f\"  verdict: {d['verdict']}\")
print(f\"  {f['address']}  [{f['category']}]\")
print()
import textwrap
print(textwrap.fill(f['explanation'], 56, initial_indent='  ', subsequent_indent='  '))"
hold 30

# ── 2:20 the experiment we removed ──────────────────────────────────────────
banner "Iteration 1: add the terraform plan. Same case."
python -c "
import json,pathlib,textwrap
def gist(t, cap=230):
    out=''
    for part in t.replace('. ', '.|').split('|'):
        if out and len(out)+len(part) > cap: break
        out = (out+' '+part).strip()
    return out
for m,l in [('oneshot-haiku','WITHOUT plan'),('i1plan-haiku','WITH plan   ')]:
    d=json.loads(pathlib.Path(f'results/findings/{m}/08.json').read_text())
    f=d['findings'][0]
    print(f'  {l}  {d[\"verdict\"]:<6} {f[\"address\"]}  [{f[\"category\"].upper()}]')
    print(textwrap.fill(gist(f['explanation']), 54, initial_indent='     ', subsequent_indent='     '))
    if m=='oneshot-haiku': print()"
hold 40

banner "Across all fifteen cases"
printf '  without the plan   F1 0.784\n  with the plan      F1 0.674\n\n  Removed.\n'
hold 14

# ── 3:05 the change that contributed most ───────────────────────────────────
banner "The same configuration, run four times, unchanged"
for m in oneshot-haiku oneshot-haiku-r2 oneshot-haiku-r3 oneshot-haiku-r4; do
  printf '  '; python score.py --mode "$m" | grep '^precision'
  hold 3
done
hold 30

# ── 4:05 final comparison ───────────────────────────────────────────────────
banner "Everything measured"
cat <<'TABLE'
                                              F1        $/PR
  Checkov, scoped to the change              0.320       $0
  One prompt, Haiku 4.5          (n=4)       0.784       $0.007
  + terraform plan               (n=4)       0.674       $0.009
  + multi-agent split            (n=4)       0.653       $0.026
  + tools and free exploration   (n=4)       0.588       $0.133

  Nothing beat one prompt.
TABLE
hold 46

banner "github.com/Jamesokooboh/blast-radius"
hold 8

rm -rf results/findings/demo results/trajectories/demo report/metrics-demo.json 2>/dev/null || true
