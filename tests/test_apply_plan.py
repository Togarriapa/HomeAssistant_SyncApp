from pathlib import Path
import tempfile
import unittest

from syncapp.transaction import build_apply_plan


class ApplyPlanTests(unittest.TestCase):
    def test_unchanged_files_are_not_rewritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            live.mkdir()
            staging.mkdir()
            (live / "configuration.yaml").write_text("same: true\n", encoding="utf-8")
            (staging / "configuration.yaml").write_text("same: true\n", encoding="utf-8")
            (live / "automations.yaml").write_text("old: true\n", encoding="utf-8")
            (staging / "automations.yaml").write_text("new: true\n", encoding="utf-8")

            plan = build_apply_plan(
                staging,
                {"configuration.yaml", "automations.yaml"},
                "a" * 40,
                live_dir=live,
            )

            self.assertEqual(plan.write_paths, ("automations.yaml",))
            self.assertEqual(plan.delete_paths, ())

    def test_removed_baseline_file_is_deleted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            live.mkdir()
            staging.mkdir()
            (live / "configuration.yaml").write_text("same: true\n", encoding="utf-8")
            (staging / "configuration.yaml").write_text("same: true\n", encoding="utf-8")
            (live / "obsolete.yaml").write_text("old: true\n", encoding="utf-8")

            plan = build_apply_plan(
                staging,
                {"configuration.yaml", "obsolete.yaml"},
                "b" * 40,
                live_dir=live,
            )

            self.assertEqual(plan.write_paths, ())
            self.assertEqual(plan.delete_paths, ("obsolete.yaml",))

    def test_new_remote_file_is_written(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            live.mkdir()
            staging.mkdir()
            (staging / "scripts.yaml").write_text("new: true\n", encoding="utf-8")

            plan = build_apply_plan(staging, set(), "c" * 40, live_dir=live)

            self.assertEqual(plan.write_paths, ("scripts.yaml",))
            self.assertEqual(plan.delete_paths, ())


if __name__ == "__main__":
    unittest.main()
