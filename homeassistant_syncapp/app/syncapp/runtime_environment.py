from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path
import stat
import tempfile


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
_AMBIENT_GIT_TLS_CLIENT_CREDENTIAL_KEYS = (
    "GIT_SSL_CERT",
    "GIT_SSL_KEY",
    "GIT_SSL_CERT_PASSWORD_PROTECTED",
    "GIT_SSL_CERT_TYPE",
    "GIT_SSL_KEY_TYPE",
    "GIT_PROXY_SSL_CERT",
    "GIT_PROXY_SSL_KEY",
    "GIT_PROXY_SSL_CERT_PASSWORD_PROTECTED",
)
_AMBIENT_CA_KEYS = ("CURL_CA_BUNDLE", "SSL_CERT_FILE", "SSL_CERT_DIR")
_SYSTEM_CA_BUNDLE = Path("/etc/ssl/certs/ca-certificates.crt")
_SYSTEM_CA_PATH = Path("/etc/ssl/certs")
_TRUSTED_CA_SNAPSHOT = Path("/data/trusted-git-ca-bundle.pem")
_MAX_CUSTOM_CA_BYTES = 2 * 1024 * 1024


class RuntimeEnvironmentError(RuntimeError):
    pass


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


def scrub_ambient_git_tls_client_credentials(
    environment: MutableMapping[str, str] | None = None,
) -> None:
    """Remove inherited Git TLS client-certificate and private-key selectors."""

    target = os.environ if environment is None else environment
    for key in _AMBIENT_GIT_TLS_CLIENT_CREDENTIAL_KEYS:
        target.pop(key, None)


def _read_custom_ca_bundle(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise RuntimeEnvironmentError("trusted Git CA bundle cannot be opened safely") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeEnvironmentError("trusted Git CA bundle must be a regular file")
        if metadata.st_size > _MAX_CUSTOM_CA_BYTES:
            raise RuntimeEnvironmentError("trusted Git CA bundle exceeds the 2 MiB safety limit")
        chunks: list[bytes] = []
        remaining = _MAX_CUSTOM_CA_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > _MAX_CUSTOM_CA_BYTES:
            raise RuntimeEnvironmentError("trusted Git CA bundle exceeds the 2 MiB safety limit")
        if not content:
            raise RuntimeEnvironmentError("trusted Git CA bundle is empty")
        return content
    finally:
        os.close(fd)


def _write_ca_snapshot(content: bytes, snapshot_path: Path) -> None:
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=".trusted-git-ca-", dir=snapshot_path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as handle:
            fd = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, snapshot_path)
    finally:
        if fd >= 0:
            os.close(fd)
        temporary_path.unlink(missing_ok=True)


def configure_git_ca_trust(
    custom_bundle: Path | None,
    environment: MutableMapping[str, str] | None = None,
    *,
    system_bundle: Path = _SYSTEM_CA_BUNDLE,
    system_ca_path: Path = _SYSTEM_CA_PATH,
    snapshot_path: Path = _TRUSTED_CA_SNAPSHOT,
) -> None:
    """Bind Git CA trust to the image trust store plus an optional trusted snapshot."""

    if custom_bundle is None:
        if not system_bundle.is_file() or not system_ca_path.is_dir():
            raise RuntimeEnvironmentError("system Git CA trust store is unavailable")
        selected_bundle = system_bundle
    else:
        content = _read_custom_ca_bundle(custom_bundle)
        _write_ca_snapshot(content, snapshot_path)
        selected_bundle = snapshot_path
        if not system_ca_path.is_dir():
            raise RuntimeEnvironmentError("system Git CA directory is unavailable")

    target = os.environ if environment is None else environment
    for key in _AMBIENT_CA_KEYS:
        target.pop(key, None)
    target["GIT_SSL_CAINFO"] = str(selected_bundle)
    target["GIT_SSL_CAPATH"] = str(system_ca_path)
