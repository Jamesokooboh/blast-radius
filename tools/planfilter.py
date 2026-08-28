"""Drop phantom changes from a Terraform plan.

Some resources -- `aws_db_instance` is the one in this stack -- always report an
in-place update when the prior state was synthesized rather than produced by a
real apply, even though every attribute before and after is identical. It is an
artefact of the fixture, not a change, and it would otherwise appear in the
input of every single case.

The rule is deliberately narrow and provable: an update whose `before` equals
its `after` is not a change. Replaces, destroys, creates, and updates that
actually alter an attribute are all untouched, so no real finding can be hidden
by this -- including the replace in case 08, which changes storage_encrypted.
"""


def is_phantom(change):
    c = change.get("change", {})
    if c.get("actions") != ["update"]:
        return False
    return c.get("before") == c.get("after")


def strip_phantoms(plan):
    """Return (plan, dropped_addresses) with phantom updates removed."""
    kept, dropped = [], []
    for ch in plan.get("resource_changes", []):
        if is_phantom(ch):
            dropped.append(ch["address"])
        else:
            kept.append(ch)
    plan["resource_changes"] = kept
    return plan, dropped


def real_changes(plan):
    """Addresses and actions of every change that is not a no-op or a phantom."""
    return [
        (c["address"], "/".join(c["change"]["actions"]))
        for c in plan.get("resource_changes", [])
        if c.get("change", {}).get("actions") != ["no-op"] and not is_phantom(c)
    ]


def _selfcheck():
    same = {"address": "aws_db_instance.main",
            "change": {"actions": ["update"], "before": {"a": 1}, "after": {"a": 1}}}
    real = {"address": "aws_db_instance.main",
            "change": {"actions": ["update"], "before": {"a": 1}, "after": {"a": 2}}}
    repl = {"address": "aws_db_instance.main",
            "change": {"actions": ["delete", "create"], "before": {"a": 1}, "after": {"a": 2}}}
    noop = {"address": "aws_vpc.main",
            "change": {"actions": ["no-op"], "before": {}, "after": {}}}

    assert is_phantom(same) and not is_phantom(real) and not is_phantom(repl)
    plan = {"resource_changes": [same, real, repl, noop]}
    _, dropped = strip_phantoms(dict(plan))
    assert dropped == ["aws_db_instance.main"], dropped
    assert len(real_changes(plan)) == 2, real_changes(plan)
    print("planfilter selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
