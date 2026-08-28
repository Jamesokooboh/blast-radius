# Serve the marketing site from S3

Marketing wants to publish the static site straight from the bucket instead of
going through the app. Adding a public read policy and relaxing the public
access block on the marketing bucket only.

The bucket holds compiled site assets: HTML, CSS, images. No customer data has
ever been written to it.
