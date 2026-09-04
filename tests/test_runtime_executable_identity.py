from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUN_SCRIPT = REPOSITORY_ROOT / "homeassistant_syncapp" / "run.sh"
DOCKERFILE = REPOSITORY_ROOT / "homeassistant_syncapp" / "Dockerfile"


class RuntimeExecutableIdentityTests(unittest.TestCase):
    def test_run_script_constrains_path_before_starting_python(self) -> None:
        text = RUN_SCRIPT.read_text(encoding="utf-8")
        path_guard = 'export PATH="/usr/bin:/bin"'
        clean_exec = "exec /usr/bin/env -i"
        python_exec = "/usr/bin/python3 -E -s -B /app/main.py"

        self.assertIn(path_guard, text)
        self.assertIn(clean_exec, text)
        self.assertIn(python_exec, text)
        self.assertLess(text.index(path_guard), text.index(clean_exec))
        self.assertLess(text.index(clean_exec), text.index(python_exec))
        self.assertNotIn("exec python3 /app/main.py", text)
        self.assertNotIn("exec /usr/bin/python3 /app/main.py", text)

    def test_run_script_scrubs_python_code_loading_overrides_before_startup(self) -> None:
        text = RUN_SCRIPT.read_text(encoding="utf-8")
        scrub = (
            "unset PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONINSPECT "
            "PYTHONBREAKPOINT PYTHONPYCACHEPREFIX"
        )
        no_user_site = 'export PYTHONNOUSERSITE="1"'
        clean_exec = "exec /usr/bin/env -i"

        self.assertIn(scrub, text)
        self.assertIn(no_user_site, text)
        self.assertLess(text.index(scrub), text.index(clean_exec))
        self.assertLess(text.index(no_user_site), text.index(clean_exec))

    def test_run_script_scrubs_dynamic_loader_overrides_before_clean_environment_exec(self) -> None:
        text = RUN_SCRIPT.read_text(encoding="utf-8")
        scrub = (
            "unset LD_PRELOAD LD_LIBRARY_PATH LD_AUDIT LD_DEBUG LD_DEBUG_OUTPUT "
            "LD_PROFILE LD_PROFILE_OUTPUT"
        )
        clean_exec = "exec /usr/bin/env -i"

        self.assertIn(scrub, text)
        self.assertLess(text.index(scrub), text.index(clean_exec))

    def test_python_process_environment_is_allowlisted(self) -> None:
        text = RUN_SCRIPT.read_text(encoding="utf-8")
        clean_exec = "exec /usr/bin/env -i"
        python_exec = "/usr/bin/python3 -E -s -B /app/main.py"
        allowlisted = (
            'PATH="/usr/bin:/bin"',
            'PYTHONNOUSERSITE="1"',
            'SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN-}"',
            'TZ="${TZ-}"',
            'LANG="${LANG-}"',
            'LC_ALL="${LC_ALL-}"',
        )

        self.assertIn(clean_exec, text)
        for assignment in allowlisted:
            self.assertIn(assignment, text)
            self.assertLess(text.index(clean_exec), text.index(assignment))
            self.assertLess(text.index(assignment), text.index(python_exec))
        self.assertNotIn('HOME="${HOME-}"', text)
        self.assertNotIn('LD_PRELOAD="${LD_PRELOAD-}"', text)
        self.assertNotIn('PYTHONPATH="${PYTHONPATH-}"', text)
        self.assertNotIn('HTTPS_PROXY="${HTTPS_PROXY-}"', text)

    def test_python_startup_ignores_environment_user_site_and_bytecode_writes(self) -> None:
        text = RUN_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("/usr/bin/python3 -E -s -B /app/main.py", text)

    def test_image_build_verifies_pinned_runtime_executables(self) -> None:
        text = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("test -x /usr/bin/env", text)
        self.assertIn("test -x /usr/bin/git", text)
        self.assertIn("test -x /usr/bin/python3", text)


if __name__ == "__main__":
    unittest.main()
