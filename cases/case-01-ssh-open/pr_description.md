# Allow SSH to app instances for on-call

On-call could not get onto the app boxes during Tuesday's incident and had to
wait for someone with VPN access to wake up. Opening 22 on the app security
group so the rotation can get in directly.

Follow-up ticket INFRA-2291 will move this behind Session Manager.
