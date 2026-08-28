# Let the BI tool reach the production database

The analytics team's Metabase instance runs outside our VPC and cannot reach
the database. Setting `publicly_accessible = true` so they can connect while we
work out VPC peering.
