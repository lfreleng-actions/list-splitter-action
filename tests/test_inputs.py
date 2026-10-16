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
ISSUE = categories.REGISTRY["issue"]


class ResolveInputsTest(unittest.TestCase):
    """validate and ignore-case accept their documented spellings alone."""

    def test_mode_defaults_to_none_and_ignores_case_and_padding(self) -> None:
        """Blank selects none; the value is trimmed and case-folded."""
        self.assertIs(inputs.resolve_category(""), NONE)
        self.assertIs(inputs.resolve_category(" Repository "), REPOSITORY)

    def test_unknown_mode_is_refused(self) -> None:
        """A typo fails rather than silently skipping validation."""
        with self.assertRaisesRegex(
            inputs.InputError,
            "one of issue, none, organisation, pull-request, repository, user,",
        ):
            inputs.resolve_category("repo")

    def test_auto_follows_the_mode(self) -> None:
        """auto, or blank, ignores case for GitHub names, not free-form tokens."""
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


class ResolveOwnerTest(unittest.TestCase):
    """owner falls back to the workflow's owner, and must be a login."""

    def test_input_wins_over_the_workflow_owner(self) -> None:
        """An owner given is used, trimmed; blank takes the workflow's."""
        self.assertEqual(inputs.resolve_owner(" octo-org ", "mine", ISSUE), "octo-org")
        self.assertEqual(inputs.resolve_owner("  ", "mine", ISSUE), "mine")

    def test_owner_must_be_a_login(self) -> None:
        """A value that no account could hold is refused."""
        for value in ("octo/org", "-octo", "x" * 40):
            with self.subTest(value=value):
                with self.assertRaises(inputs.InputError):
                    inputs.resolve_owner(value, "mine", ISSUE)

    def test_categories_without_owners_ignore_the_input(self) -> None:
        """Free-form and account lists need no owner, so get none."""
        for name in ("none", "organisation", "user"):
            with self.subTest(name=name):
                category = categories.REGISTRY[name]
                self.assertEqual(inputs.resolve_owner("a b!", "", category), "")

    def test_only_references_require_an_owner(self) -> None:
        """Bare repository names read without one; repo#N cannot."""
        self.assertEqual(inputs.resolve_owner("", "", REPOSITORY), "")
        with self.assertRaisesRegex(inputs.InputError, "owner is blank"):
            inputs.resolve_owner("", "", ISSUE)


class ReadSettingsTest(unittest.TestCase):
    """Settings gather every input, with the runner's server address."""

    def test_server_url_comes_from_the_runner(self) -> None:
        """GITHUB_SERVER_URL sets the URL prefix; github.com without one."""
        environ = {"SPLIT_VALIDATE": "issue", "GITHUB_REPOSITORY_OWNER": "o"}
        self.assertEqual(
            inputs.read_settings(environ).context.server_url, "https://github.com"
        )
        environ["GITHUB_SERVER_URL"] = "https://ghes.example.com"
        self.assertEqual(
            inputs.read_settings(environ).context.server_url, "https://ghes.example.com"
        )


if __name__ == "__main__":
    unittest.main()
