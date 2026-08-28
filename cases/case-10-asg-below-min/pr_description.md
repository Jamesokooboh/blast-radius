# Scale the app fleet down to one instance overnight

Traffic between midnight and 6am is a rounding error and we are paying for three
instances to serve it. Dropping desired capacity to 1.
