"""Research-only exact direct-payment profile eligibility diagnostics."""

from __future__ import annotations

from collections import Counter

from research.stage3.profile_compilers.direct_payment_v1 import DIRECT_PAYMENT_PROFILE
from research.stage3.profiles import ProfileRegistry


def direct_payment_profile_match(spec: dict) -> str:
    registry_status = ProfileRegistry([DIRECT_PAYMENT_PROFILE]).match(spec)[0].value
    if registry_status != "EXACT_SUPPORTED_PROFILE":
        return registry_status
    claims = spec.get("claims")
    if (not isinstance(claims, list) or len(claims) != 4
            or not all(isinstance(claim, dict) for claim in claims)
            or Counter(claim.get("kind") for claim in claims) != Counter(
                {kind: 1 for kind in DIRECT_PAYMENT_PROFILE.claim_kinds})):
        return "UNSUPPORTED_PROFILE"
    return "EXACT_SUPPORTED_PROFILE"
