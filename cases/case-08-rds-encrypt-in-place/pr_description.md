# Enable encryption at rest on the production database

Closes INFRA-1804. The security review flagged that the production Postgres
instance is unencrypted at rest, which we need to fix before the SOC 2 window
closes at the end of the month.

One-line change: `storage_encrypted = true`.
