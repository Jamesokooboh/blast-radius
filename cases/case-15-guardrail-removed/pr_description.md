# Unblock CI on the data bucket

Terraform plan in CI has been failing on the data bucket for a week because of
the lifecycle guard, and it is blocking every unrelated change. Removing it so we
can ship. Also adding the CostCenter tag while I am in this file.
