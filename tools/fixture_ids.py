"""Plausible AWS identifiers for the state fixture.

Terraform validates some ids at plan time (a launch template id must look like
`lt-...`), and any resource whose `arn` is null in state breaks every reference
to it. So the fixture needs identifiers with the right shape rather than
placeholders. These are deterministic functions of the resource address, so the
generated state is byte-identical on every machine.

Nothing here corresponds to a real AWS account. The account id is all zeros.
"""

import hashlib

ACCOUNT = "000000000000"
REGION = "us-east-1"


def _h(address, n=16):
    return hashlib.sha256(address.encode()).hexdigest()[:n]


def _named(attrs, *keys, default="fixture"):
    for k in keys:
        if attrs.get(k):
            return attrs[k]
    return default


# id formats that Terraform or a consuming resource actually validates.
_PREFIXED = {
    "aws_vpc": "vpc-0",
    "aws_subnet": "subnet-0",
    "aws_internet_gateway": "igw-0",
    "aws_nat_gateway": "nat-0",
    "aws_eip": "eipalloc-0",
    "aws_route_table": "rtb-0",
    "aws_route_table_association": "rtbassoc-0",
    "aws_security_group": "sg-0",
    "aws_launch_template": "lt-0",
    "aws_network_interface": "eni-0",
    "aws_instance": "i-0",
}

# resources whose id is simply their name
_BY_NAME = {
    "aws_autoscaling_group": ("name",),
    "aws_db_subnet_group": ("name",),
    "aws_iam_role": ("name",),
    "aws_iam_instance_profile": ("name",),
    "aws_s3_bucket": ("bucket",),
    "aws_s3_bucket_versioning": ("bucket",),
    "aws_s3_bucket_lifecycle_configuration": ("bucket",),
    "aws_s3_bucket_public_access_block": ("bucket",),
    "aws_s3_bucket_server_side_encryption_configuration": ("bucket",),
    "aws_s3_bucket_policy": ("bucket",),
    "aws_db_instance": ("identifier",),
}


def make_id(rtype, address, attrs):
    if rtype in _PREFIXED:
        return _PREFIXED[rtype] + _h(address)
    if rtype in _BY_NAME:
        return _named(attrs, *_BY_NAME[rtype], default=address.split(".")[-1])
    if rtype == "aws_iam_role_policy":
        return f"{_named(attrs, 'role')}:{_named(attrs, 'name')}"
    if rtype in ("aws_lb", "aws_lb_target_group", "aws_lb_listener"):
        return make_arn(rtype, address, attrs)
    return f"fixture-{_h(address, 12)}"


def make_arn(rtype, address, attrs):
    name = _named(attrs, "name", "bucket", "identifier", default=address.split(".")[-1])
    elb = f"arn:aws:elasticloadbalancing:{REGION}:{ACCOUNT}"

    if rtype == "aws_lb":
        return f"{elb}:loadbalancer/app/{name}/{_h(address)}"
    if rtype == "aws_lb_target_group":
        return f"{elb}:targetgroup/{name}/{_h(address)}"
    if rtype == "aws_lb_listener":
        return f"{elb}:listener/app/{name}/{_h(address)}/{_h(address + '!')}"
    if rtype == "aws_s3_bucket":
        return f"arn:aws:s3:::{name}"
    if rtype == "aws_db_instance":
        return f"arn:aws:rds:{REGION}:{ACCOUNT}:db:{name}"
    if rtype == "aws_db_subnet_group":
        return f"arn:aws:rds:{REGION}:{ACCOUNT}:subgrp:{name}"
    if rtype == "aws_iam_role":
        return f"arn:aws:iam::{ACCOUNT}:role/{name}"
    if rtype == "aws_iam_instance_profile":
        return f"arn:aws:iam::{ACCOUNT}:instance-profile/{name}"
    if rtype == "aws_security_group":
        return f"arn:aws:ec2:{REGION}:{ACCOUNT}:security-group/{attrs.get('id', _h(address))}"
    if rtype == "aws_launch_template":
        return f"arn:aws:ec2:{REGION}:{ACCOUNT}:launch-template/{attrs.get('id', _h(address))}"
    if rtype == "aws_autoscaling_group":
        return (
            f"arn:aws:autoscaling:{REGION}:{ACCOUNT}:autoScalingGroup:"
            f"{_h(address, 8)}:autoScalingGroupName/{name}"
        )
    if rtype == "aws_subnet":
        return f"arn:aws:ec2:{REGION}:{ACCOUNT}:subnet/{attrs.get('id', _h(address))}"
    if rtype == "aws_vpc":
        return f"arn:aws:ec2:{REGION}:{ACCOUNT}:vpc/{attrs.get('id', _h(address))}"
    return f"arn:aws:fixture:{REGION}:{ACCOUNT}:{rtype}/{name}"


# Types with an `arn` attribute. planned_values omits keys that are unknown at
# plan time, so the attribute is absent rather than null and has to be added.
_HAS_ARN = {
    "aws_lb", "aws_lb_target_group", "aws_lb_listener", "aws_s3_bucket",
    "aws_db_instance", "aws_db_subnet_group", "aws_iam_role",
    "aws_iam_instance_profile", "aws_security_group", "aws_launch_template",
    "aws_autoscaling_group", "aws_subnet", "aws_vpc", "aws_internet_gateway",
}


def fill(rtype, address, attrs):
    """Fill the attributes that are unknown until apply but referenced by others."""
    if not attrs.get("id"):
        attrs["id"] = make_id(rtype, address, attrs)
    if (rtype in _HAS_ARN or "arn" in attrs) and not attrs.get("arn"):
        attrs["arn"] = make_arn(rtype, address, attrs)
    # tags_all is computed from tags; leaving it unset diffs forever.
    if "tags" in attrs and not attrs.get("tags_all"):
        attrs["tags_all"] = attrs.get("tags") or {}
    return attrs
