#!/usr/bin/env python3
"""Build a Terraform state fixture offline, without applying anything.

Why this exists: `terraform plan` against an empty state reports every resource
as `create`, so the plan-transition cases -- a replace that destroys a database,
a guardrail quietly removed -- cannot occur at all. Those are exactly the cases
a static scanner structurally cannot see, which makes them the point of the
project. They need prior state.

Rather than standing up LocalStack or hand-writing state, this derives state
from the plan's own planned_values, fills the identifiers that are only known
after apply (see fixture_ids.py), then converges: write state, re-plan, fold the
proposed changes back in, repeat until the plan is a clean no-op.

Runs against a temporary copy with `prevent_destroy` stripped -- the guardrail
would abort convergence, and it is a config property that state does not record.

Run once. Commit fixtures/base.tfstate. Judges never run this.
"""

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fixture_ids  # noqa: E402
import planfilter  # noqa: E402

PROVIDER = 'provider["registry.terraform.io/hashicorp/aws"]'
PREVENT_DESTROY = re.compile(r"^\s*prevent_destroy\s*=\s*true\s*$", re.MULTILINE)


def tf(workdir, *args, check=True):
    r = subprocess.run(["terraform", *args], cwd=workdir, capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"terraform {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}")
    return r


def plan_json(workdir):
    r = tf(workdir, "plan", "-refresh=false", "-input=false", "-no-color", "-out=tfplan", check=False)
    if r.returncode != 0:
        return None, r.stdout + r.stderr
    return json.loads(tf(workdir, "show", "-json", "tfplan").stdout), None


def stage(src, dst):
    """Copy the config to a scratch dir, minus the lifecycle guards."""
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.tf"):
        dst.joinpath(f.name).write_text(PREVENT_DESTROY.sub("", f.read_text()))
    for extra in (".terraform", ".terraform.lock.hcl"):
        s = src / extra
        if s.is_dir():
            shutil.copytree(s, dst / extra, dirs_exist_ok=True)
        elif s.exists():
            shutil.copy2(s, dst / extra)


def build_state(planned, terraform_version):
    resources = []
    for r in planned.get("planned_values", {}).get("root_module", {}).get("resources", []):
        attrs = fixture_ids.fill(r["type"], r["address"], dict(r.get("values") or {}))
        inst = {"schema_version": r.get("schema_version", 0), "attributes": attrs,
                "sensitive_attributes": []}
        if "index" in r:
            inst["index_key"] = r["index"]
        resources.append({"mode": r.get("mode", "managed"), "type": r["type"],
                          "name": r["name"], "provider": PROVIDER, "instances": [inst]})
    return {
        "version": 4,
        "terraform_version": terraform_version,
        "serial": 1,
        "lineage": str(uuid.uuid5(uuid.NAMESPACE_DNS, "blast-radius-fixture")),
        "outputs": {},
        "resources": resources,
        "check_results": None,
    }


def _zero(typespec):
    """Smallest value of the right shape for a computed attribute."""
    if isinstance(typespec, str):
        return {"string": "", "number": 0, "bool": False}.get(typespec, None)
    if isinstance(typespec, list) and typespec:
        if typespec[0] in ("list", "set"):
            return []
        if typespec[0] in ("map", "object"):
            return {}
    return None


def load_schema(workdir):
    """type -> (schema_version, {attribute: zero value}).

    Attributes that are computed-only stay unknown forever if state leaves them
    null, so the plan never reaches a no-op. The provider schema is the only
    place that knows their shape.
    """
    raw = json.loads(tf(workdir, "providers", "schema", "-json").stdout)
    out = {}
    for prov in raw.get("provider_schemas", {}).values():
        for rtype, rs in prov.get("resource_schemas", {}).items():
            block = rs.get("block", {})
            zeros = {}
            for attr, spec in block.get("attributes", {}).items():
                z = _zero(spec.get("type"))
                if z is not None:
                    zeros[attr] = z
            for blk, spec in block.get("block_types", {}).items():
                zeros[blk] = {} if spec.get("nesting_mode") == "single" else []
            out[rtype] = (rs.get("version", 0), zeros)
    return out


def fill_unknowns(state, plan, schema):
    """Give every still-unknown attribute a value of the right shape."""
    unknown = {c["address"]: (c["change"].get("after_unknown") or {})
               for c in plan.get("resource_changes", [])}
    for res in state["resources"]:
        _, zeros = schema.get(res["type"], (0, {}))
        for inst in res["instances"]:
            addr = f"{res['type']}.{res['name']}"
            for attr, flag in unknown.get(addr, {}).items():
                if flag is False or attr in ("id", "arn"):
                    continue
                if inst["attributes"].get(attr) in (None, ...) and attr in zeros:
                    inst["attributes"][attr] = zeros[attr]


def _key(rtype, name, index):
    return (rtype, name, json.dumps(index, sort_keys=True))


def fold(state, plan):
    """Merge the plan's proposed values back into state, then re-fill unknowns."""
    idx = {}
    for res in state["resources"]:
        for inst in res["instances"]:
            idx[_key(res["type"], res["name"], inst.get("index_key"))] = (res, inst)

    n = 0
    for ch in plan.get("resource_changes", []):
        if ch.get("change", {}).get("actions") == ["no-op"]:
            continue
        hit = idx.get(_key(ch["type"], ch["name"], ch.get("index")))
        if not hit:
            continue
        res, inst = hit
        for k, v in (ch["change"].get("after") or {}).items():
            if v is not None:
                inst["attributes"][k] = v
        fixture_ids.fill(res["type"], ch["address"], inst["attributes"])
        n += 1
    return n


def pending(plan):
    """Changes still to reconcile. Phantom updates are not changes -- see planfilter."""
    return planfilter.real_changes(plan)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-rounds", type=int, default=10)
    args = ap.parse_args()

    src = pathlib.Path(args.dir).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp) / "base"
        stage(src, work)

        plan, err = plan_json(work)
        if err:
            sys.exit("initial plan failed:\n" + err)
        schema = load_schema(work)
        state = build_state(plan, plan.get("terraform_version", "1.9.0"))
        for res in state["resources"]:
            version, _ = schema.get(res["type"], (0, {}))
            for inst in res["instances"]:
                inst["schema_version"] = version
        print(f"seeded {len(state['resources'])} resources from planned_values")

        statefile = work / "terraform.tfstate"
        for rnd in range(1, args.max_rounds + 1):
            statefile.write_text(json.dumps(state, indent=2))
            plan, err = plan_json(work)
            if err:
                sys.exit(f"round {rnd}: plan failed:\n{err}")
            left = pending(plan)
            if not left:
                out = pathlib.Path(args.out).resolve()
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(state, indent=2))
                print(f"round {rnd}: clean no-op -> {out}")
                return 0
            print(f"round {rnd}: {len(left)} differ; folding")
            for addr, act in left[:8]:
                print(f"   {act:>18}  {addr}")
            state["serial"] += 1
            folded = fold(state, plan)
            fill_unknowns(state, plan, schema)
            if folded == 0:
                break

        print("\nDID NOT CONVERGE:", file=sys.stderr)
        for addr, act in pending(plan):
            print(f"   {act:>18}  {addr}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
