# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Unit tests for list_splitter.categories."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from list_splitter import categories  # noqa: E402
from list_splitter.categories.base import Category, Context, InvalidItem, Item  # noqa: E402

CONTEXT = Context("lfreleng-actions", "https://github.com")


class CategoryTestCase(unittest.TestCase):
    """Assertions shared by the tests of each category."""

    def assertRefused(
        self, category: Category, token: str, reason: str, context: Context = CONTEXT
    ) -> None:
        """The category refuses the token, giving exactly this reason."""
        with self.assertRaises(InvalidItem) as caught:
            category.parse(token, context)
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

    def test_spellings_share_one_category(self) -> None:
        """Both spellings of organisation select the same category."""
        self.assertIs(
            categories.REGISTRY["organization"], categories.REGISTRY["organisation"]
        )


class AnyTokenTest(CategoryTestCase):
    """The none mode accepts every token unchanged."""

    def test_accepts_anything(self) -> None:
        """Globs, owners and stray characters all pass, with no details."""
        none = categories.REGISTRY["none"]
        for token in ("*-workflows", "owner/repo", "50%", "é"):
            with self.subTest(token=token):
                self.assertEqual(none.parse(token, CONTEXT), Item(token))


class RepositoryTest(CategoryTestCase):
    """The repository mode accepts bare names GitHub would accept."""

    category = categories.REGISTRY["repository"]

    def test_accepts_valid_names(self) -> None:
        """Letters, digits, dots, dashes and underscores pass."""
        for name in (".github", "a", "repo_1.x-y", "x" * 100):
            with self.subTest(name=name):
                self.assertEqual(
                    self.category.parse(name, CONTEXT),
                    Item(name, owner="lfreleng-actions", repo=name),
                )

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


class NumberedReferenceTest(CategoryTestCase):
    """Issues and pull requests share every spelling but the path segment."""

    pull = categories.REGISTRY["pull-request"]
    issue = categories.REGISTRY["issue"]

    def test_every_spelling_names_the_same_pull_request(self) -> None:
        """Short, long and URL forms, any case and padding of the number."""
        expected = Item(
            "lfreleng-actions/repo#7", owner="lfreleng-actions", repo="repo", number=7
        )
        for token in (
            "repo#7",
            "lfreleng-actions/repo#007",
            "repo/pull/7",
            "LFReleng-Actions/repo/pull/7/",
            "https://github.com/lfreleng-actions/repo/pull/7",
            "HTTPS://GitHub.com/lfreleng-actions/repo/pull/7/",
            "https://github.com/lfreleng-actions/repo/pull/7#issuecomment-9",
            "https://github.com/lfreleng-actions/repo/pull/7?notification_referrer_id=1",
        ):
            with self.subTest(token=token):
                self.assertEqual(self.pull.parse(token, CONTEXT), expected)

    def test_urls_follow_the_server(self) -> None:
        """On GitHub Enterprise Server, its own address is the URL prefix."""
        server = Context("octo-org", "https://ghes.example.com/")
        self.assertEqual(
            self.issue.parse(
                "https://ghes.example.com/octo-org/repo/issues/2", server
            ).text,
            "octo-org/repo#2",
        )
        self.assertRefused(
            self.issue,
            "https://github.com/octo-org/repo/issues/2",
            "not a valid reference to an issue",
            server,
        )

    def test_url_prefixes_compare_in_ascii(self) -> None:
        """A letter that folds to ASCII does not make a GitHub address."""
        self.assertRefused(
            self.issue,
            "http\u017f://github.com/lfreleng-actions/repo/issues/2",
            "not a valid reference to an issue",
        )

    def test_numbers_stay_within_a_graphql_int(self) -> None:
        """The largest 32-bit number passes; one more, or zero, does not."""
        self.assertEqual(
            self.issue.parse("repo#2147483647", CONTEXT).text,
            "lfreleng-actions/repo#2147483647",
        )
        for number in ("0", "2147483648", "99999999999", "-1", "1e3", "٣"):
            with self.subTest(number=number):
                self.assertRefused(
                    self.issue, f"repo#{number}", "not a valid issue number"
                )

    def test_shapes_that_are_not_references(self) -> None:
        """Missing parts and extra segments are not references at all."""
        for token in (
            "repo",
            "#5",
            "/repo#5",
            "repo#",
            "a/b/c/d/e",
            "repo#1/",
            "o/r/pull/1/files",
        ):
            with self.subTest(token=token):
                self.assertRefused(
                    self.pull, token, "not a valid reference to a pull request"
                )


class AccountTest(CategoryTestCase):
    """Organisations and users are logins, judged by structure alone."""

    user = categories.REGISTRY["user"]

    def test_accepts_valid_logins(self) -> None:
        """Hyphens anywhere but first, underscores, and 39 characters pass.

        a--b--t and johan-- are real accounts that GitHub's signup form
        would now refuse, so the check must not.
        """
        for login in (
            "a",
            "octocat",
            "a--b--t",
            "johan--",
            "mona_acme",
            "a_",
            "x" * 39,
        ):
            with self.subTest(login=login):
                self.assertEqual(
                    self.user.parse(login, CONTEXT), Item(login, login=login)
                )

    def test_refuses_invalid_logins(self) -> None:
        """A leading hyphen, stray characters and 40 characters fail."""
        for login in ("-a", "_a", "a.b", "é", "x" * 40, "org/name"):
            with self.subTest(login=login):
                self.assertRefused(self.user, login, "not a valid user name")


if __name__ == "__main__":
    unittest.main()
