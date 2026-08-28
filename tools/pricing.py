"""A small price table, and a monthly cost delta for a plan's changed resources.

Deliberately crude. It prices the handful of resource types in this fixture at
approximate us-east-1 on-demand list rates and ignores everything usage-based
(data transfer, S3 storage, LCUs, IOPS). The purpose is not to be an accounting
system: it is to put a number in front of the reviewer for the category every
configuration measured so far keeps dropping.

Known limitation, stated because it bounds what I4 can recover: this prices
resources being created and destroyed. A resource that becomes *useless* without
being destroyed -- the NAT gateway in case 09, orphaned when its subnets move to
another route table -- has no cost delta here, and I4 cannot be expected to find
it. Case 11 is the one it should reach.

    python tools/pricing.py    # self-check
"""

HOURS = 730.0

# $/hour for a resource that simply exists, by Terraform type.
HOURLY = {
    "aws_nat_gateway": 0.045,
    "aws_lb": 0.0225,
    "aws_eip": 0.005,
}

# $/hour by instance class, for the types that take one.
DB_HOURLY = {
    "db.t3.micro": 0.017, "db.t3.small": 0.034,
    "db.t3.medium": 0.068, "db.m5.large": 0.171,
}
EC2_HOURLY = {
    "t3.micro": 0.0104, "t3.small": 0.0208,
    "t3.medium": 0.0416, "m5.large": 0.096,
}

GP3_PER_GB_MONTH = 0.08


def monthly(rtype, values):
    """Approximate $/month for one resource in the state the plan describes."""
    if values is None:
        return 0.0
    if rtype in HOURLY:
        return HOURLY[rtype] * HOURS

    if rtype == "aws_db_instance":
        rate = DB_HOURLY.get(values.get("instance_class"), 0.0)
        cost = rate * HOURS * (2 if values.get("multi_az") else 1)
        cost += (values.get("allocated_storage") or 0) * GP3_PER_GB_MONTH
        return cost

    if rtype == "aws_autoscaling_group":
        # Priced at desired capacity; the launch template's instance type is not
        # in this resource, so callers pass it in via values["_instance_type"].
        rate = EC2_HOURLY.get(values.get("_instance_type", ""), 0.0)
        return rate * HOURS * (values.get("desired_capacity") or 0)

    return 0.0


def delta_for_plan(changes, instance_type=None):
    """[(address, actions, $/month before, after, delta)] plus the total."""
    rows, total = [], 0.0
    for c in changes:
        actions = c.get("change", {}).get("actions", [])
        before = dict(c["change"].get("before") or {})
        after = dict(c["change"].get("after") or {})
        if instance_type:
            before["_instance_type"] = after["_instance_type"] = instance_type

        b = 0.0 if "create" in actions and "delete" not in actions else monthly(c["type"], before)
        a = 0.0 if actions == ["delete"] else monthly(c["type"], after)
        if abs(a - b) < 0.01:
            continue
        rows.append((c["address"], "/".join(actions), b, a, a - b))
        total += a - b
    return rows, total


def as_text(changes, instance_type=None):
    rows, total = delta_for_plan(changes, instance_type)
    if not rows:
        return "  No change to the monthly cost of the resources in this plan."
    lines = [f"  {addr:<42} {act:<14} ${b:>8.2f} -> ${a:>8.2f}   {a-b:+9.2f}"
             for addr, act, b, a in [(r[0], r[1], r[2], r[3]) for r in rows]]
    lines.append("")
    lines.append(f"  {'estimated monthly change':<42} {'':<14} {'':>10} {'':>11} "
                 f"{total:+9.2f}")
    lines.append(f"  {'estimated annual change':<42} {'':<14} {'':>10} {'':>11} "
                 f"{total * 12:+9.2f}")
    return "\n".join(lines)


def _selfcheck():
    nat = {"address": "aws_nat_gateway.b", "type": "aws_nat_gateway",
           "change": {"actions": ["create"], "before": None, "after": {}}}
    rows, total = delta_for_plan([nat])
    assert len(rows) == 1, rows
    assert 32 < total < 34, total          # ~$32.85/month for one NAT gateway

    # A destroy is a saving, not a charge.
    gone = {"address": "aws_lb.old", "type": "aws_lb",
            "change": {"actions": ["delete"], "before": {}, "after": None}}
    _, t2 = delta_for_plan([gone])
    assert -17 < t2 < -16, t2

    # A replacement of an identical resource nets to nothing and is not listed.
    same = {"address": "aws_db_instance.main", "type": "aws_db_instance",
            "change": {"actions": ["delete", "create"],
                       "before": {"instance_class": "db.t3.medium",
                                  "allocated_storage": 100, "multi_az": True},
                       "after": {"instance_class": "db.t3.medium",
                                 "allocated_storage": 100, "multi_az": True}}}
    rows3, t3 = delta_for_plan([same])
    assert rows3 == [] and t3 == 0.0, (rows3, t3)

    # A resource this table does not know about prices at zero, not at a guess.
    unknown = {"address": "aws_route_table.x", "type": "aws_route_table",
               "change": {"actions": ["create"], "before": None, "after": {}}}
    assert delta_for_plan([unknown]) == ([], 0.0)

    print("pricing selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
