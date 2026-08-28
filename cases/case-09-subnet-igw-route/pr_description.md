# Give the app subnets direct internet access

The vendor API we integrate with rate-limits by source IP, and our NAT gateway's
single address keeps getting throttled. Pointing the app subnets at the public
route table so instances egress directly.
