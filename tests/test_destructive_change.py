import unittest

from syncapp.destructive_change import (
    DestructiveChangeError,
    enforce_remote_deletion_budget,
)


class RemoteDeletionBudgetTests(unittest.TestCase):
    def test_allows_candidate_within_absolute_and_percentage_budgets(self) -> None:
        baseline = {f"packages/{index}.yaml" for index in range(10)}
        result = enforce_remote_deletion_budget(
            ("packages/0.yaml", "packages/1.yaml"),
            baseline,
            max_deletions=5,
            max_deletion_percent=25,
        )
        self.assertEqual(result.deleted_paths, 2)
        self.assertEqual(result.baseline_paths, 10)
        self.assertEqual(result.deletion_percent, 20.0)

    def test_rejects_candidate_over_absolute_budget(self) -> None:
        baseline = {f"packages/{index}.yaml" for index in range(100)}
        with self.assertRaisesRegex(DestructiveChangeError, "3 deletions"):
            enforce_remote_deletion_budget(
                ("packages/0.yaml", "packages/1.yaml", "packages/2.yaml"),
                baseline,
                max_deletions=2,
                max_deletion_percent=100,
            )

    def test_rejects_candidate_over_percentage_budget(self) -> None:
        baseline = {"configuration.yaml", "automations.yaml", "scripts.yaml"}
        with self.assertRaisesRegex(DestructiveChangeError, "66.7%"):
            enforce_remote_deletion_budget(
                ("automations.yaml", "scripts.yaml"),
                baseline,
                max_deletions=10,
                max_deletion_percent=50,
            )

    def test_boundary_is_inclusive(self) -> None:
        baseline = {"configuration.yaml", "automations.yaml"}
        result = enforce_remote_deletion_budget(
            ("automations.yaml",),
            baseline,
            max_deletions=1,
            max_deletion_percent=50,
        )
        self.assertEqual(result.deletion_percent, 50.0)

    def test_zero_budget_blocks_any_remote_deletion(self) -> None:
        with self.assertRaises(DestructiveChangeError):
            enforce_remote_deletion_budget(
                ("automations.yaml",),
                {"configuration.yaml", "automations.yaml"},
                max_deletions=0,
                max_deletion_percent=100,
            )


if __name__ == "__main__":
    unittest.main()
