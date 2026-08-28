#!/usr/bin/env bash
# Build the plan JSON and the pull request diff for one case, or for all of them.
#
#   ./plan.sh base       # the unchanged stack; must be a clean no-op
#   ./plan.sh 08         # one case
#   ./plan.sh --all
#
# Needs Terraform and network access once, to fetch the provider. No AWS
# account, no credentials, no cost.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export TF_PLUGIN_CACHE_DIR="$ROOT/.plugin-cache"
mkdir -p "$TF_PLUGIN_CACHE_DIR" "$ROOT/results/plans" "$ROOT/results/diffs"

case_dir() {
  local id="$1"
  find "$ROOT/cases" -maxdepth 1 -type d -name "case-${id}-*" | head -1
}

plan_one() {
  local id="$1"
  local work="$ROOT/.work/$id"
  local dir=""

  if [ "$id" != "base" ]; then
    dir="$(case_dir "$id")"
    [ -n "$dir" ] || { echo "no such case: $id" >&2; return 1; }
  fi

  rm -rf "$work"; mkdir -p "$work"
  cp "$ROOT"/infra/base/*.tf "$work"/
  [ -f "$ROOT/infra/base/.terraform.lock.hcl" ] && cp "$ROOT/infra/base/.terraform.lock.hcl" "$work"/

  # The overlay is the pull request: whole files that replace their base version.
  if [ -n "$dir" ] && [ -d "$dir/overlay" ]; then
    cp "$dir"/overlay/*.tf "$work"/
  fi

  # Prior state is what makes replace and destroy actions possible at all.
  cp "$ROOT/fixtures/base.tfstate" "$work/terraform.tfstate"

  terraform -chdir="$work" init -backend=false -input=false -no-color >/dev/null
  terraform -chdir="$work" plan -refresh=false -input=false -no-color \
    -out="$work/tfplan" > "$work/plan.txt"
  terraform -chdir="$work" show -json "$work/tfplan" > "$work/plan.raw.json"

  echo "--- case $id ---"
  python "$ROOT/tools/emit_plan.py" \
    --raw "$work/plan.raw.json" \
    --out "$ROOT/results/plans/$id.plan.json"

  # The diff the reviewer would see on the pull request.
  local diff="$ROOT/results/diffs/$id.diff"
  : > "$diff"
  if [ -n "$dir" ] && [ -d "$dir/overlay" ]; then
    for f in "$dir"/overlay/*.tf; do
      git --no-pager diff --no-index --no-color -- \
        "$ROOT/infra/base/$(basename "$f")" "$f" >> "$diff" || true
    done
  fi
}

if [ "${1:-}" = "--all" ]; then
  plan_one base
  for d in "$ROOT"/cases/case-*/; do
    id="$(basename "$d" | sed -E 's/^case-([0-9]+)-.*/\1/')"
    plan_one "$id"
  done
else
  plan_one "${1:?usage: plan.sh base|<case-id>|--all}"
fi
