from __future__ import annotations

import os
from collections.abc import MutableMapping


_AMBIENT_PROXY_KEYS = (
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
)


def scrub_ambient_proxy_environment(
    environment: MutableMapping[str, str] | None = None,
) -> None:
    """Remove inherited proxy routing from the SyncApp process environment.

    SyncApp does not currently expose a trusted proxy configuration option. Allowing
    add-on/container environment variables to select an HTTP(S) proxy would make the
    GitHub transport path depend on ambient runtime state rather than explicit
    SyncApp configuration. Until proxy support has an explicit trust contract, fail
    closed by using direct transport.
    """

    target = os.environ if environment is None else environment
    for key in _AMBIENT_PROXY_KEYS:
        target.pop(key, None)


def lock_git_tls_negotiation_defaults(
    environment: MutableMapping[str, str] | None = None,
) -> None:
    """Force Git/libcurl to use its compiled default TLS version and cipher policy."""

    target = os.environ if environment is None else environment
    target["GIT_SSL_VERSION"] = ""
    target["GIT_SSL_CIPHER_LIST"] = ""
