# Internal load balancer for service-to-service traffic

The worker fleet currently calls the API through the public load balancer,
which means internal traffic leaves and re-enters the VPC. Adding an internal
ALB on the private subnets so those calls stay inside.
