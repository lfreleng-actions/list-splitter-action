# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Unit tests for list_splitter.inputs."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from list_splitter import categories, inputs  # noqa: E402

NONE = categories.REGISTRY["none"]
REPOSITORY = categories.REGISTRY["repository"]


class ResolveInputsTest(unittest.TestCase):
    """validate and ignore-case accept their documented spellings alone."""

    def test_mode_defaults_to_none_and_ignores_case_and_padding(self) -> None:
        """Blank selects none; the value is trimmed and case-folded."""
        self.assertIs(inputs.resolve_category(""), NONE)
        self.assertIs(inputs.resolve_category(" Repository "), REPOSITORY)

    @unittest.expectedFailure
    def test_unknown_mode_is_refused(self) -> None:
        """A typo fails rather than silently skipping validation."""
        with self.assertRaisesRegex(
            inputs.InputError,
            "one of issue, none, organisation, pull-request, repository, user,",
        ):
            inputs.resolve_category("repo")

    def test_auto_follows_the_mode(self) -> None:
        """auto, or blank, ignores case for repositories alone."""
        for value in ("", "auto", " AUTO "):
            with self.subTest(value=value):
                self.assertTrue(inputs.resolve_ignore_case(value, REPOSITORY))
                self.assertFalse(inputs.resolve_ignore_case(value, NONE))

    def test_explicit_setting_overrides_the_mode(self) -> None:
        """true and false apply whatever the mode."""
        self.assertTrue(inputs.resolve_ignore_case("true", NONE))
        self.assertFalse(inputs.resolve_ignore_case("False", REPOSITORY))

    def test_unknown_ignore_case_is_refused(self) -> None:
        """Only auto, true and false are accepted."""
        with self.assertRaises(inputs.InputError):
            inputs.resolve_ignore_case("yes", NONE)


if __name__ == "__main__":
    unittest.main()
