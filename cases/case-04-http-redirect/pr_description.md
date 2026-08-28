# Redirect plain HTTP to HTTPS

People typing the hostname without a scheme currently get a connection refused.
Adding a listener on 80 that 301s to the HTTPS listener, and opening 80 on the
load balancer security group so the redirect is reachable.
