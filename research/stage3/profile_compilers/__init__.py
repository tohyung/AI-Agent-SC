"""Conservative deterministic compiler profiles for explicitly configured runs."""

from research.stage3.profile_compilers.direct_payment_v1 import (
    DIRECT_PAYMENT_PROFILE, compile_direct_payment_v1,
)
from research.stage3.profile_compilers.funded_choice_v1 import (
    FUNDED_CHOICE_PROFILE, compile_funded_choice_v1,
)
from research.stage3.profile_compilers.funded_swap_v1 import (
    FUNDED_SWAP_PROFILE, compile_funded_swap_v1,
)
from research.stage3.profile_compilers.linear_time_release_v1 import (
    LINEAR_TIME_RELEASE_PROFILE, compile_linear_time_release_v1,
)
from research.stage3.profile_compilers.sequential_approval_v1 import (
    SEQUENTIAL_APPROVAL_PROFILE, compile_sequential_approval_v1,
)
from research.stage3.profiles import ProfileRegistry


def configured_compilers() -> tuple[ProfileRegistry, dict]:
    pairs = (
        (DIRECT_PAYMENT_PROFILE, compile_direct_payment_v1),
        (FUNDED_CHOICE_PROFILE, compile_funded_choice_v1),
        (FUNDED_SWAP_PROFILE, compile_funded_swap_v1),
        (LINEAR_TIME_RELEASE_PROFILE, compile_linear_time_release_v1),
        (SEQUENTIAL_APPROVAL_PROFILE, compile_sequential_approval_v1),
    )
    return (ProfileRegistry([profile for profile, _ in pairs]),
            {(profile.profile_id, profile.version): compiler
             for profile, compiler in pairs})
