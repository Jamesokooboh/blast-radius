variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name_prefix" {
  type    = string
  default = "acme-prod"
}

# Passed in rather than looked up, so that `terraform plan` needs no API access.
variable "app_ami_id" {
  type    = string
  default = "ami-0fixture00000000"
}

variable "certificate_arn" {
  type    = string
  default = "arn:aws:acm:us-east-1:000000000000:certificate/fixture"
}

variable "availability_zones" {
  type    = list(string)
  default = ["us-east-1a", "us-east-1b"]
}

# Buckets the application role may read and write. Consumed by iam.tf.
variable "app_data_bucket_arns" {
  type = list(string)
  default = [
    "arn:aws:s3:::acme-prod-data",
    "arn:aws:s3:::acme-prod-data/*",
  ]
}
