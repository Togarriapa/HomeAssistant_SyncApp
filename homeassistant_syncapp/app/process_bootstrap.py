from __future__ import annotations

import os
from collections.abc import Mapping


PYTHON_EXECUTABLE = "/usr/bin/python3"
MAIN_SCRIPT = "/app/main.py"
_PRESERVED_ENVIRONMENT = ("SUPERVISOR_TOKEN", "TZ", "LANG", "LC_ALL")


def build_service_environment(source: Mapping[str, str]) -> dict[str, str]:
    """Construct the exact environment inherited by the long-lived service."""
    environment = {
        "PATH": "/usr/bin:/bin",
        "PYTHONNOUSERSITE": "1",
    }
    for name in _PRESERVED_ENVIRONMENT:
        if name in source:
            environment[name] = source[name]
    return environment


def main() -> int:
    environment = build_service_environment(os.environ)
    arguments = [PYTHON_EXECUTABLE, "-E", "-s", "-B", MAIN_SCRIPT]
    os.execve(PYTHON_EXECUTABLE, arguments, environment)
    raise RuntimeError("os.execve unexpectedly returned")


if __name__ == "__main__":
    raise SystemExit(main())
