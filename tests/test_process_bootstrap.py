import os
import unittest
from unittest.mock import patch

import process_bootstrap


class ProcessBootstrapTests(unittest.TestCase):
    def test_service_environment_is_exact_allowlist(self) -> None:
        source = {
            "SUPERVISOR_TOKEN": "super-secret",
            "TZ": "Europe/Lisbon",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "HOME": "/attacker/home",
            "HTTPS_PROXY": "http://attacker.invalid:8080",
            "GIT_DIR": "/attacker/git",
            "PYTHONPATH": "/attacker/python",
            "LD_PRELOAD": "/attacker/lib.so",
            "BASH_ENV": "/attacker/bashrc",
        }

        environment = process_bootstrap.build_service_environment(source)

        self.assertEqual(
            environment,
            {
                "PATH": "/usr/bin:/bin",
                "PYTHONNOUSERSITE": "1",
                "SUPERVISOR_TOKEN": "super-secret",
                "TZ": "Europe/Lisbon",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
            },
        )

    def test_optional_locale_values_are_not_invented(self) -> None:
        environment = process_bootstrap.build_service_environment(
            {"SUPERVISOR_TOKEN": "token"}
        )

        self.assertEqual(
            environment,
            {
                "PATH": "/usr/bin:/bin",
                "PYTHONNOUSERSITE": "1",
                "SUPERVISOR_TOKEN": "token",
            },
        )

    def test_main_execs_pinned_python_without_putting_token_in_argv(self) -> None:
        inherited = {
            "SUPERVISOR_TOKEN": "super-secret",
            "HTTPS_PROXY": "http://attacker.invalid:8080",
            "LD_PRELOAD": "/attacker/lib.so",
        }
        with patch.dict(os.environ, inherited, clear=True), patch(
            "process_bootstrap.os.execve", side_effect=RuntimeError("stop")
        ) as execve:
            with self.assertRaisesRegex(RuntimeError, "stop"):
                process_bootstrap.main()

        executable, arguments, environment = execve.call_args.args
        self.assertEqual(executable, "/usr/bin/python3")
        self.assertEqual(
            arguments,
            ["/usr/bin/python3", "-E", "-s", "-B", "/app/main.py"],
        )
        self.assertNotIn("super-secret", arguments)
        self.assertEqual(environment["SUPERVISOR_TOKEN"], "super-secret")
        self.assertNotIn("HTTPS_PROXY", environment)
        self.assertNotIn("LD_PRELOAD", environment)


if __name__ == "__main__":
    unittest.main()
