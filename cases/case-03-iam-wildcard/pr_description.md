# Add a deploy role for CodeBuild

Our pipeline needs a role it can assume to run deployments. Broad permissions
for now so we stop getting blocked on missing actions mid-deploy; we will scope
it down once we know exactly what it touches.
