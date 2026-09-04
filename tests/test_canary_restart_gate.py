import unittest

from canary import run_canary


class CanaryRestartGateTests(unittest.TestCase):
    def test_restart_requires_fresh_backup_before_any_supervisor_call(self):
        with self.assertRaisesRegex(
            RuntimeError,
            "refusing canary Core restart without a fresh inventory-verified backup",
        ):
            run_canary(object(), restart=True)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
