from __future__ import annotations

import os
from collections.abc import MutableMapping


def lock_git_no_lazy_fetch(
    environment: MutableMapping[str, str] | None = None,
) -> None:
    """Require missing Git object evidence to fail locally instead of fetching it."""

    target = os.environ if environment is None else environment
    target["GIT_NO_LAZY_FETCH"] = "1"


def lock_git_optional_locks(
    environment: MutableMapping[str, str] | None = None,
) -> None:
    """Disable optional Git operations that may mutate repository bookkeeping."""

    target = os.environ if environment is None else environment
    target["GIT_OPTIONAL_LOCKS"] = "0"


def lock_git_protocol_from_user(
    environment: MutableMapping[str, str] | None = None,
) -> None:
    """Prevent Git from enabling user-classified protocols from ambient context."""

    target = os.environ if environment is None else environment
    target["GIT_PROTOCOL_FROM_USER"] = "0"


def lock_git_literal_pathspecs(
    environment: MutableMapping[str, str] | None = None,
) -> None:
    """Require program-supplied Git pathspecs to be interpreted literally."""

    target = os.environ if environment is None else environment
    for key in ("GIT_GLOB_PATHSPECS", "GIT_NOGLOB_PATHSPECS", "GIT_ICASE_PATHSPECS"):
        target.pop(key, None)
    target["GIT_LITERAL_PATHSPECS"] = "1"


def scrub_git_allow_protocol(
    environment: MutableMapping[str, str] | None = None,
) -> None:
    """Remove ambient protocol whitelists that override Git protocol configuration."""

    target = os.environ if environment is None else environment
    target.pop("GIT_ALLOW_PROTOCOL", None)


def lock_git_history_paranoia(
    environment: MutableMapping[str, str] | None = None,
) -> None:
    """Fail closed on broken refs and stale commit-graph object references."""

    target = os.environ if environment is None else environment
    target["GIT_REF_PARANOIA"] = "1"
    target["GIT_COMMIT_GRAPH_PARANOIA"] = "1"
