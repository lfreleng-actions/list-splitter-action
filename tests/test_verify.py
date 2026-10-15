# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""End-to-end tests of the verify input, against a stand-in for GitHub."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from action_harness import ActionTestCase, read_outputs  # noqa: E402
from fake_github import FakeGitHub  # noqa: E402
from list_splitter.graphql import GitHubError  # noqa: E402

TOKEN = "ghs_not-a-real-token"
NOT_FOUND = "not found on GitHub, or not visible to the token"


class VerifyTest(ActionTestCase):
    """verify confirms each item on GitHub and reports what it found."""

    def setUp(self) -> None:
        """Provide a GitHub holding a few objects of every kind."""
        super().setUp()
        self.fake = FakeGitHub()
        self.transport = self.fake
        self.fake.add_repository("lfreleng-actions", "repo-a")
        self.fake.add_repository(
            "lfreleng-actions",
            "empty",
            defaultBranchRef=None,
            isPrivate=True,
            visibility="INTERNAL",
        )
        self.fake.add_numbered("lfreleng-actions", "repo-a", 1, "Issue")
        self.fake.add_numbered(
            "lfreleng-actions", "repo-a", 2, "PullRequest", isDraft=True
        )
        self.fake.add_numbered(
            "lfreleng-actions", "repo-a", 3, "PullRequest", state="MERGED"
        )
        self.fake.add_account("lfreleng-actions", "Organization")
        self.fake.add_account("octocat", "User")

    def verify(self, validate: str, items: str) -> tuple[int, str]:
        """Run main with verification on."""
        return self.run_main(list=items, validate=validate, verify="true", token=TOKEN)

    def details(self) -> list[dict[str, Any]]:
        """The details output, decoded."""
        return json.loads(read_outputs(self.path)["details"])

    def test_repositories_report_what_discovery_reads(self) -> None:
        """Details gain the fields that choose what to scan, as REST names them."""
        status, log = self.verify("repository", "repo-a Empty")
        self.assertEqual(status, 0)
        self.assertEqual(log.splitlines()[0], "Verified on GitHub with 1 GraphQL query")
        repo_a, empty = self.details()
        self.assertEqual(
            repo_a,
            {
                "item": "repo-a",
                "owner": "lfreleng-actions",
                "repo": "repo-a",
                "html_url": "https://github.com/lfreleng-actions/repo-a",
                "default_branch": "main",
                "archived": False,
                "fork": False,
                "is_template": False,
                "disabled": False,
                "private": False,
                "visibility": "public",
            },
        )
        self.assertEqual(
            (empty["default_branch"], empty["private"], empty["visibility"]),
            (None, True, "internal"),
        )

    def test_pull_requests_report_state_and_draft(self) -> None:
        """Each pull request's details carry its state and draft flag."""
        status, _ = self.verify("pull-request", "repo-a#2 repo-a/pull/3")
        self.assertEqual(status, 0)
        base = "https://github.com/lfreleng-actions/repo-a/pull"
        self.assertEqual(
            [(d["state"], d["draft"], d["html_url"]) for d in self.details()],
            [("open", True, f"{base}/2"), ("merged", False, f"{base}/3")],
        )

    def test_accounts_report_their_page(self) -> None:
        """Organisations and users gain the address of their page."""
        status, _ = self.verify("user", "OctoCat")
        self.assertEqual(status, 0)
        self.assertEqual(
            self.details(),
            [
                {
                    "item": "OctoCat",
                    "login": "OctoCat",
                    "html_url": "https://github.com/octocat",
                }
            ],
        )

    def test_each_mismatch_names_its_reason(self) -> None:
        """Absent objects, the other kind, and the other account type each say so."""
        for validate, items, refusals in (
            ("repository", "nope", [("nope", NOT_FOUND)]),
            (
                "issue",
                "repo-a#2 repo-a#9 nope#1",
                [
                    ("lfreleng-actions/repo-a#2", "is a pull request, not an issue"),
                    ("lfreleng-actions/repo-a#9", NOT_FOUND),
                    (
                        "lfreleng-actions/nope#1",
                        f"repository lfreleng-actions/nope {NOT_FOUND}",
                    ),
                ],
            ),
            (
                "pull-request",
                "repo-a#1",
                [("lfreleng-actions/repo-a#1", "is an issue, not a pull request")],
            ),
            (
                "organisation",
                "octocat",
                [("octocat", "is a user, not an organisation")],
            ),
            (
                "user",
                "lfreleng-actions",
                [("lfreleng-actions", "is an organisation, not a user")],
            ),
        ):
            with self.subTest(validate=validate):
                status, log = self.verify(validate, items)
                self.assertEqual(status, 1)
                self.assertRefusals(log, refusals)

    def test_moved_objects_are_refused_with_their_new_place(self) -> None:
        """A renamed repository, or a transferred issue, names where it went."""
        self.fake.add_repository("lfreleng-actions", "old-name")
        self.fake.repositories[("lfreleng-actions", "old-name")]["nameWithOwner"] = (
            "elsewhere/new-name"
        )
        self.fake.add_numbered(
            "lfreleng-actions",
            "repo-a",
            4,
            "Issue",
            repository={"nameWithOwner": "elsewhere/other"},
        )
        status, log = self.verify("repository", "old-name")
        self.assertEqual(status, 1)
        self.assertRefusals(log, [("old-name", "has moved to elsewhere/new-name")])
        status, log = self.verify("issue", "repo-a#4")
        self.assertEqual(status, 1)
        self.assertRefusals(
            log, [("lfreleng-actions/repo-a#4", "has moved to elsewhere/other#4")]
        )

    def test_offline_and_online_failures_are_reported_together(self) -> None:
        """Valid tokens are verified even when others fail, for one re-run."""
        status, log = self.verify("repository", "bad! nope repo-a")
        self.assertEqual(status, 1)
        self.assertRefusals(
            log, [("bad!", "not a valid repository name"), ("nope", NOT_FOUND)]
        )

    def test_an_outage_fails_without_blaming_the_items(self) -> None:
        """When GitHub cannot answer, the run fails as an operational error."""

        def down(payload: dict[str, Any]) -> dict[str, Any]:
            raise GitHubError("GitHub answered HTTP 503: unavailable, after 3 attempts")

        self.transport = down
        status, log = self.verify("repository", "repo-a bad!")
        self.assertEqual(status, 1)
        self.assertEqual(
            log.splitlines(),
            [
                "::error::Invalid item 'bad!': not a valid repository name",
                "::error::Could not verify the items on GitHub: GitHub answered"
                " HTTP 503: unavailable, after 3 attempts",
            ],
        )
        self.assertEqual(self.path.read_text(encoding="utf-8"), "")

    def test_a_blank_list_sends_no_query(self) -> None:
        """Nothing to verify costs nothing."""
        status, _ = self.verify("repository", " , ")
        self.assertEqual(status, 0)
        self.assertEqual(self.fake.queries, [])

    def test_the_inputs_verify_needs_are_checked_first(self) -> None:
        """A bad setting, a free-form mode, a blank token or plain HTTP all fail."""
        for inputs, runner, message in (
            ({"verify": "yes"}, {}, "verify must be true or false, not 'yes'"),
            (
                {"verify": "true", "validate": "none"},
                {},
                "verify needs a mode naming GitHub objects, not none",
            ),
            (
                {"verify": "true", "token": " "},
                {},
                "verify needs a token, and the token input is blank",
            ),
            (
                {"verify": "true", "token": "ghs_two\nlines"},
                {},
                "the token input holds characters no GitHub token has",
            ),
            (
                {"verify": "true"},
                {"GITHUB_GRAPHQL_URL": "http://ghes.example.com/api/graphql"},
                "GITHUB_GRAPHQL_URL must use https, not 'http://ghes.example.com/api/graphql'",
            ),
            (
                {"verify": "true"},
                {"GITHUB_GRAPHQL_URL": "", "GITHUB_REPOSITORY_OWNER": ""},
                "owner is blank, and GITHUB_REPOSITORY_OWNER is not set",
            ),
        ):
            with self.subTest(inputs=inputs, runner=runner):
                self.runner.update(runner)
                arguments = {"list": "repo-a", "validate": "repository", "token": TOKEN}
                arguments.update(inputs)
                status, log = self.run_main(**arguments)
                self.assertEqual((status, log), (1, f"::error::{message}\n"))
                self.assertEqual(self.fake.queries, [])

    def test_the_token_never_reaches_the_log(self) -> None:
        """Neither success, failure nor a malformed token prints the token."""
        for items in ("repo-a", "nope"):
            with self.subTest(items=items):
                _, log = self.verify("repository", items)
                self.assertNotIn(TOKEN, log)
        _, log = self.run_main(
            list="repo-a", validate="repository", verify="true", token=f"{TOKEN}\u00e9"
        )
        self.assertNotIn(TOKEN, log)

    def test_a_missing_account_is_not_found(self) -> None:
        """GitHub answers a missing login with a bare null, and no error."""
        status, log = self.verify("user", "ghost-zz9")
        self.assertEqual(status, 1)
        self.assertRefusals(log, [("ghost-zz9", NOT_FOUND)])


if __name__ == "__main__":
    unittest.main()
