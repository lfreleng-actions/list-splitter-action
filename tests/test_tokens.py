# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Unit tests for list_splitter.tokens."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from list_splitter import tokens  # noqa: E402


class SplitTest(unittest.TestCase):
    """Commas and every kind of whitespace separate items."""

    def test_mixed_separators(self) -> None:
        """Commas, spaces, tabs and newlines all split; runs collapse."""
        self.assertEqual(
            tokens.split("a, b c,,d\te\nf\r\n g ,"),
            ["a", "b", "c", "d", "e", "f", "g"],
        )

    def test_blank_and_separator_only_input_yield_nothing(self) -> None:
        """Input holding no item gives an empty list, never an empty item."""
        for text in ("", "   ", ",", " , ,\n\t"):
            with self.subTest(text=text):
                self.assertEqual(tokens.split(text), [])

    def test_items_keep_their_characters(self) -> None:
        """Splitting alters nothing within an item, globs included."""
        self.assertEqual(
            tokens.split("*-workflows ci-[ab]? owner/repo"),
            ["*-workflows", "ci-[ab]?", "owner/repo"],
        )


class DedupeTest(unittest.TestCase):
    """Repeats collapse to the first occurrence, keeping order."""

    def test_exact_comparison(self) -> None:
        """Without ignore-case, items differing in case are distinct."""
        self.assertEqual(
            tokens.dedupe(["b", "A", "b", "a", "A"], str, ignore_case=False),
            ["b", "A", "a"],
        )

    def test_case_insensitive_comparison_keeps_first_spelling(self) -> None:
        """With ignore-case, the first spelling given survives."""
        self.assertEqual(
            tokens.dedupe(["Repo", "other", "REPO", "repo"], str, ignore_case=True),
            ["Repo", "other"],
        )

    def test_the_key_decides_what_repeats(self) -> None:
        """Entries repeat when their keys match, whatever else they hold."""
        entries = [("x", 1), ("y", 2), ("X", 3), ("y", 4)]
        self.assertEqual(
            tokens.dedupe(entries, lambda entry: entry[0], ignore_case=True),
            [("x", 1), ("y", 2)],
        )


if __name__ == "__main__":
    unittest.main()
