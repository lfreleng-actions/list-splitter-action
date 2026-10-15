# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Unit tests for list_splitter.categories."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from list_splitter import categories  # noqa: E402
from list_splitter.categories.base import Category, InvalidItem  # noqa: E402


class CategoryTestCase(unittest.TestCase):
    """Assertions shared by the tests of each category."""

    def assertRefused(self, category: Category, token: str, reason: str) -> None:
        """The category refuses the token, giving exactly this reason."""
        with self.assertRaises(InvalidItem) as caught:
            category.parse(token)
        self.assertEqual(str(caught.exception), reason)


class RegistryTest(unittest.TestCase):
    """Each validate input spelling resolves to one category."""

    def test_names_are_unique(self) -> None:
        """No two categories claim the same spelling."""
        spellings = [name for c in categories.CATEGORIES for name in c.names]
        self.assertEqual(len(categories.REGISTRY), len(spellings))

    def test_names_are_lower_case(self) -> None:
        """The input is lower-cased before lookup, so names must be too."""
        for name in categories.REGISTRY:
            with self.subTest(name=name):
                self.assertEqual(name, name.lower())


class AnyTokenTest(CategoryTestCase):
    """The none mode accepts every token unchanged."""

    def test_accepts_anything(self) -> None:
        """Globs, owners and stray characters all pass."""
        none = categories.REGISTRY["none"]
        for token in ("*-workflows", "owner/repo", "50%", "é"):
            with self.subTest(token=token):
                self.assertEqual(none.parse(token), token)


class RepositoryTest(CategoryTestCase):
    """The repository mode accepts bare names GitHub would accept."""

    category = categories.REGISTRY["repository"]

    def test_accepts_valid_names(self) -> None:
        """Letters, digits, dots, dashes and underscores pass."""
        for name in (".github", "a", "repo_1.x-y", "x" * 100):
            with self.subTest(name=name):
                self.assertEqual(self.category.parse(name), name)

    def test_refuses_an_owner_prefix_by_name(self) -> None:
        """owner/name gets its own message, the likeliest mistake."""
        self.assertRefused(
            self.category,
            "lfreleng-actions/repo",
            "give the repository name alone, without the owner",
        )

    def test_refuses_invalid_names(self) -> None:
        """Path segments, stray characters and over-long names fail."""
        for name in (".", "..", "repo?", "*-workflows", "re po!", "é", "x" * 101):
            with self.subTest(name=name):
                self.assertRefused(self.category, name, "not a valid repository name")


if __name__ == "__main__":
    unittest.main()
