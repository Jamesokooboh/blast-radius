# One NAT gateway per availability zone

A single NAT gateway is a single point of failure: if us-east-1a goes down, the
private subnets in 1b lose egress too. Adding a second NAT gateway in 1b with its
own route table.
