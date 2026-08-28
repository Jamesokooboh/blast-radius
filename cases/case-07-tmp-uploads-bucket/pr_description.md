# Staging bucket for browser uploads

Uploads currently go straight into the data bucket and the worker validates them
in place, which means bad files land next to good ones. Adding a staging bucket
with a one-day expiry: uploads land here, the worker validates and moves them,
and anything left after 24 hours was a failed upload.
