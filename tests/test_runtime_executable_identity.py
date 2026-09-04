from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUN_SCRIPT = REPOSITORY_ROOT / "homeassistant_syncapp" / "run.sh"
DOCKERFILE = REPOSITORY_ROOT / "homeassistant_syncapp" / "Dockerfile"


class RuntimeExecutableIdentityTests(unittest.TestCase):
    def test_run_script_constrains_path_before_starting_python(self) -> None:
        text = RUN_SCRIPT.read_text(encoding="utf-8")
        path_guard = 'export PATH="/usr/bin:/bin"'
        python_exec = "exec /usr/bin/python3 -E -s -B /app/main.py"

        self.assertIn(path_guard, text)
        self.assertIn(python_exec, text)
        self.assertLess(text.index(path_guard), text.index(python_exec))
        self.assertNotIn("exec python3 /app/main.py", text)
        self.assertNotIn("exec /usr/bin/python3 /app/main.py", text)

    def test_run_script_scrubs_python_code_loading_overrides_before_startup(self) -> None:
        text = RUN_SCRIPT.read_text(encoding="utf-8")
        scrub = (
            "unset PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONINSPECT "
            "PYTHONBREAKPOINT PYTHONPYCACHEPREFIX"
        )
        no_user_site = 'export PYTHONNOUSERSITE="1"'
        python_exec = "exec /usr/bin/python3 -E -s -B /app/main.py"

        self.assertIn(scrub, text)
        self.assertIn(no_user_site, text)
        self.assertLess(text.index(scrub), text.index(python_exec))
        self.assertLess(text.index(no_user_site), text.index(python_exec))

    def test_run_script_scrubs_dynamic_loader_overrides_before_python_exec(self) -> None:
        text = RUN_SCRIPT.read_text(encoding="utf-8")
        scrub = (
            "unset LD_PRELOAD LD_LIBRARY_PATH LD_AUDIT LD_DEBUG LD_DEBUG_OUTPUT "
            "LD_PROFILE LD_PROFILE_OUTPUT"
        )
        python_exec = "exec /usr/bin/python3 -E -s -B /app/main.py"

        self.assertIn(scrub, text)
        self.assertLess(text.index(scrub), text.index(python_exec))

    def test_python_startup_ignores_environment_user_site_and_bytecode_writes(self) -> None:
        text = RUN_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("exec /usr/bin/python3 -E -s -B /app/main.py", text)

    def test_image_build_verifies_pinned_runtime_executables(self) -> None:
        text = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("test -x /usr/bin/git", text)
        self.assertIn("test -x /usr/bin/python3", text)


if __name__ == "__main__":
    unittest.main()
