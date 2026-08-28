"""Bedrock client, output contract, and the one call every runner makes.

Everything in this project talks to Claude through here, so the baselines and
the agent share an identical output schema and an identical model configuration.
The only thing that varies between stages is what goes into the prompt, which is
the point of the experiment.

Auth is the ordinary AWS credential chain -- no API key anywhere near the repo.
"""

import os
import pathlib
from typing import List, Literal, Optional

from anthropic import AnthropicBedrockMantle
from pydantic import BaseModel, Field

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGION = os.environ.get("AWS_REGION", "us-east-1")

# Which AWS account gets billed. Two accounts are configured on this machine, so
# the profile is explicit rather than whatever `default` happens to point at.
PROFILE = os.environ.get("AWS_PROFILE", "Joseph")

# Bedrock model ids carry an `anthropic.` prefix, and the Messages (Mantle)
# endpoint wants them UNDATED. `bedrock:ListFoundationModels` returns dated ids
# like `anthropic.claude-haiku-4-5-20251001-v1` -- those are for the legacy
# InvokeModel API and 404 here. Don't "fix" these by copying from that listing.
MODELS = {
    "sonnet": "anthropic.claude-sonnet-5",   # reported runs
    "opus": "anthropic.claude-opus-5",       # spot-checking the hard cases
    "haiku": "anthropic.claude-haiku-4-5",   # cheap runs while debugging plumbing
}

# Haiku 4.5 predates adaptive thinking and rejects output_config.effort.
LEGACY_THINKING = {"haiku"}

CATEGORIES = (
    "network-exposure",
    "privilege-escalation",
    "data-loss",
    "guardrail",
    "reliability",
    "cost",
)


class Finding(BaseModel):
    address: str = Field(description="Terraform resource address the finding is about")
    category: Literal[CATEGORIES]  # type: ignore[valid-type]
    severity: Literal["critical", "high", "medium", "low"]
    evidence: str = Field(description="The file and change, or the plan action, that shows this")
    explanation: str = Field(description="What goes wrong, in one or two sentences")


class Review(BaseModel):
    verdict: Literal["block", "warn", "approve"]
    headline: str = Field(description="The single thing that matters most, or why nothing does")
    findings: List[Finding] = Field(max_length=5)
    suppressed: Optional[str] = Field(
        default=None,
        description="Anything alarming-looking you decided not to report, and why",
    )


def use_profile(profile=None):
    """Pin the AWS profile before any client is constructed."""
    global PROFILE
    if profile:
        PROFILE = profile
    os.environ["AWS_PROFILE"] = PROFILE
    return PROFILE


def whoami():
    """Account and identity that will be billed. Printed before anything spends."""
    import boto3
    os.environ["AWS_PROFILE"] = PROFILE
    ident = boto3.Session(profile_name=PROFILE).client("sts").get_caller_identity()
    return {"profile": PROFILE, "account": ident["Account"], "arn": ident["Arn"]}


def client():
    os.environ["AWS_PROFILE"] = PROFILE
    return AnthropicBedrockMantle(aws_region=REGION)


def review_instructions():
    return (ROOT / "prompts" / "review.md").read_text(encoding="utf-8")


def call(prompt, model="sonnet", system=None, effort="high", max_tokens=8000):
    """One structured review call. Returns (Review, raw_response)."""
    if model not in MODELS:
        raise SystemExit(f"unknown model {model!r}; pick one of {list(MODELS)}")

    kwargs = dict(
        model=MODELS[model],
        max_tokens=max_tokens,
        system=system or review_instructions(),
        messages=[{"role": "user", "content": prompt}],
        output_format=Review,
    )
    if model in LEGACY_THINKING:
        # No adaptive thinking and no effort knob on this generation.
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": 2048}
    else:
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": effort}

    response = client().messages.parse(**kwargs)
    return response.parsed_output, response


def to_findings_json(review):
    """The shape score.py reads."""
    return {
        "verdict": review.verdict,
        "headline": review.headline,
        "suppressed": review.suppressed,
        "findings": [
            {
                "address": f.address,
                "category": f.category,
                "severity": f.severity,
                "evidence_ref": f.evidence,
                "explanation": f.explanation,
            }
            for f in review.findings
        ],
    }


def usage_cost(response, model="sonnet"):
    """Dollars for one call, from the response's own usage figures."""
    rates = {  # $ per million tokens, Anthropic first-party list rates
        "sonnet": (2.0, 10.0),
        "opus": (5.0, 25.0),
        "haiku": (1.0, 5.0),
    }
    rate_in, rate_out = rates[model]
    u = response.usage
    cached = getattr(u, "cache_read_input_tokens", 0) or 0
    written = getattr(u, "cache_creation_input_tokens", 0) or 0
    return (
        u.input_tokens * rate_in
        + cached * rate_in * 0.1
        + written * rate_in * 1.25
        + u.output_tokens * rate_out
    ) / 1e6
