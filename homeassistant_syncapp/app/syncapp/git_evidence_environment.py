from __future__ import annotations

import os
from collections.abc import MutableMapping


def lock_git_no_lazy_fetch(
    environment: MutableMapping[str, str] | None = None,
) -> None:
    """Require missing Git object evidence to fail locally instead of fetching it."""

    target = os.environ if environment is None else environment
    target["GIT_NO_LAZY_FETCH"] = "1"
