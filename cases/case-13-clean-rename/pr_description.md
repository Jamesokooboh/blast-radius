# Rename the artifacts bucket resource to match our naming convention

Pure refactor. `aws_s3_bucket.artifacts` becomes `aws_s3_bucket.build_artifacts`
so the Terraform address matches what everyone already calls it. `moved` blocks
included so this is a state move rather than a destroy and recreate.

No change to the bucket itself.
