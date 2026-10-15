# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Unit tests for list_splitter.outputs and list_splitter.action."""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from action_harness import (  # noqa: E402
    WORKFLOW_OWNER,
    ActionTestCase,
    OutputFileTestCase,
    read_outputs,
)
from list_splitter import action, outputs  # noqa: E402
from list_splitter.categories.base import Item  # noqa: E402


class OutputsTest(OutputFileTestCase):
    """Each output renders the same items, and the file cannot be forged."""

    def test_formats(self) -> None:
        """Every output describes the same list."""
        items = [
            Item("o/a#1", owner="o", repo="a", number=1),
            Item("o/b#2", owner="o", repo="b", number=2),
        ]
        self.assertEqual(
            outputs.build_outputs(items),
            {
                "json": '["o/a#1","o/b#2"]',
                "csv": "o/a#1,o/b#2",
                "lines": "o/a#1\no/b#2",
                "count": "2",
                "repositories": "a,b",
                "details": '[{"item":"o/a#1","owner":"o","repo":"a","number":1},'
                '{"item":"o/b#2","owner":"o","repo":"b","number":2}]',
            },
        )

    def test_repositories_are_named_once(self) -> None:
        """Items in one repository, however spelt, name it once."""
        items = [Item("r#1", repo="Repo"), Item("x"), Item("r#2", repo="repo")]
        self.assertEqual(outputs.build_outputs(items)["repositories"], "Repo")

    def test_empty_list(self) -> None:
        """No items gives empty arrays and empty text outputs."""
        outputs.write_outputs(str(self.path), outputs.build_outputs([]))
        self.assertEqual(
            read_outputs(self.path),
            {
                "json": "[]",
                "csv": "",
                "lines": "",
                "count": "0",
                "repositories": "",
                "details": "[]",
            },
        )

    def test_values_round_trip(self) -> None:
        """Multi-line and non-ASCII values read back unchanged."""
        rendered = outputs.build_outputs([Item("ä*"), Item("b")])
        outputs.write_outputs(str(self.path), rendered)
        self.assertEqual(read_outputs(self.path), rendered)
        self.assertEqual(json.loads(rendered["json"]), ["ä*", "b"])

    def test_value_cannot_inject_a_key(self) -> None:
        """A value shaped like a key line stays inside its own value."""
        hostile = "x\ncount=999\nghadelim_\ninjected<<EOF"
        outputs.write_outputs(str(self.path), {"lines": hostile})
        self.assertEqual(read_outputs(self.path), {"lines": hostile})

    def test_escape_command(self) -> None:
        """Percent signs and line breaks are encoded for the runner."""
        self.assertEqual(outputs.escape_command("50%\r\n::x"), "50%25%0D%0A::x")


class MainTest(ActionTestCase):
    """End to end: environment in, output file and log out."""

    def test_repository_list(self) -> None:
        """Names split, collapse ignoring case, and keep their order."""
        status, log = self.run_main(
            list="repo-b, Repo-A repo-a\nrepo-b", validate="repository"
        )
        self.assertEqual(status, 0)
        found = read_outputs(self.path)
        details = json.loads(found.pop("details"))
        self.assertEqual(
            found,
            {
                "json": '["repo-b","Repo-A"]',
                "csv": "repo-b,Repo-A",
                "lines": "repo-b\nRepo-A",
                "count": "2",
                "repositories": "repo-b,Repo-A",
            },
        )
        self.assertEqual(
            details,
            [
                {"item": "repo-b", "owner": WORKFLOW_OWNER, "repo": "repo-b"},
                {"item": "Repo-A", "owner": WORKFLOW_OWNER, "repo": "Repo-A"},
            ],
        )
        self.assertEqual(log, 'Items (2): ["repo-b","Repo-A"]\n')

    def test_issue_spellings_collapse_to_one_reference(self) -> None:
        """Every spelling of an issue publishes as owner/repo#N, once."""
        status, _ = self.run_main(
            list=(
                "repo-a#12 lfreleng-actions/repo-a#12, Repo-A#012\n"
                "https://github.com/LFReleng-Actions/repo-a/issues/12/ "
                "repo-b/issues/7 lfreleng-actions/repo-a/issues/3"
            ),
            validate="issue",
        )
        self.assertEqual(status, 0)
        found = read_outputs(self.path)
        self.assertEqual(
            json.loads(found["json"]),
            [
                "lfreleng-actions/repo-a#12",
                "lfreleng-actions/repo-b#7",
                "lfreleng-actions/repo-a#3",
            ],
        )
        self.assertEqual(found["count"], "3")
        self.assertEqual(found["repositories"], "repo-a,repo-b")
        self.assertEqual(
            json.loads(found["details"])[1],
            {
                "item": "lfreleng-actions/repo-b#7",
                "owner": WORKFLOW_OWNER,
                "repo": "repo-b",
                "number": 7,
            },
        )

    def test_pull_requests_resolve_against_the_owner_input(self) -> None:
        """The owner input replaces the workflow's owner for short forms."""
        status, _ = self.run_main(
            list=(
                "repo#3 octo-org/repo/pull/4 https://github.com/octo-org/other/pull/5"
            ),
            validate="pull-request",
            owner="octo-org",
        )
        self.assertEqual(status, 0)
        found = read_outputs(self.path)
        self.assertEqual(
            found["lines"], "octo-org/repo#3\nocto-org/repo#4\nocto-org/other#5"
        )
        self.assertEqual(found["repositories"], "repo,other")

    def test_invalid_references_are_each_reported(self) -> None:
        """Each refused reference gets the reason that fits it."""
        status, log = self.run_main(
            list=(
                "other-org/repo#1 repo/pull/2 repo#0 repo#2147483648 bad!#1 "
                "repo -bad/repo#1 repo/discussions/4 https://github.com/repo#5"
            ),
            validate="issue",
        )
        self.assertEqual(status, 1)
        self.assertRefusals(
            log,
            [
                ("other-org/repo#1", "belongs to other-org, not lfreleng-actions"),
                ("repo/pull/2", "names a pull request, not an issue"),
                ("repo#0", "not a valid issue number"),
                ("repo#2147483648", "not a valid issue number"),
                ("bad!#1", "not a valid repository name"),
                ("repo", "not a valid reference to an issue"),
                ("-bad/repo#1", "not a valid owner name"),
                ("repo/discussions/4", "not a valid reference to an issue"),
                ("https://github.com/repo#5", "not a valid reference to an issue"),
            ],
        )

    def test_issue_links_are_refused_as_pull_requests(self) -> None:
        """A link to an issue is not a pull request, whatever its number."""
        status, log = self.run_main(
            list="https://github.com/lfreleng-actions/repo/issues/9",
            validate="pull-request",
        )
        self.assertEqual(status, 1)
        self.assertRefusals(
            log,
            [
                (
                    "https://github.com/lfreleng-actions/repo/issues/9",
                    "names an issue, not a pull request",
                )
            ],
        )

    def test_accounts_are_logins_compared_without_case(self) -> None:
        """Organisations and users publish as given, once each."""
        for mode in ("organisation", "organization", "user"):
            with self.subTest(mode=mode):
                self.path.write_text("", encoding="utf-8")
                status, _ = self.run_main(
                    list="lfreleng-actions, LFRELENG-ACTIONS octocat", validate=mode
                )
                self.assertEqual(status, 0)
                found = read_outputs(self.path)
                self.assertEqual(found["json"], '["lfreleng-actions","octocat"]')
                self.assertEqual(found["repositories"], "")
                self.assertEqual(
                    json.loads(found["details"]),
                    [
                        {"item": "lfreleng-actions", "login": "lfreleng-actions"},
                        {"item": "octocat", "login": "octocat"},
                    ],
                )

    def test_invalid_accounts_are_each_reported(self) -> None:
        """A login GitHub could not hold is refused, naming the kind."""
        long_name = "x" * 40
        status, log = self.run_main(
            list=f"-lead dot.ted lfreleng-actions/repo {long_name}",
            validate="organisation",
        )
        self.assertEqual(status, 1)
        reason = "not a valid organisation name"
        self.assertRefusals(
            log,
            [
                ("-lead", reason),
                ("dot.ted", reason),
                ("lfreleng-actions/repo", reason),
                (long_name, reason),
            ],
        )

    def test_real_accounts_pass_whatever_the_signup_rules_say(self) -> None:
        """Accounts GitHub holds pass, though its signup form now refuses them.

        a--b--t is an organisation and johan-- a user, with consecutive
        and trailing hyphens. The offline check looks at structure alone,
        as dependamerge's owner check does; verify settles existence.
        """
        status, _ = self.run_main(list="a--b--t", validate="organisation")
        self.assertEqual(status, 0)
        self.assertEqual(read_outputs(self.path)["json"], '["a--b--t"]')
        self.path.write_text("", encoding="utf-8")
        status, _ = self.run_main(list="johan--", validate="user")
        self.assertEqual(status, 0)
        self.path.write_text("", encoding="utf-8")
        status, _ = self.run_main(list="repo#1", validate="issue", owner="johan--")
        self.assertEqual(status, 0)
        self.assertEqual(read_outputs(self.path)["json"], '["johan--/repo#1"]')

    def test_unvalidated_items_carry_bare_details(self) -> None:
        """With no validation, details name each item and nothing else."""
        status, _ = self.run_main(list="*-workflows owner/repo#1")
        self.assertEqual(status, 0)
        found = read_outputs(self.path)
        self.assertEqual(found["repositories"], "")
        self.assertEqual(
            json.loads(found["details"]),
            [{"item": "*-workflows"}, {"item": "owner/repo#1"}],
        )

    def test_owner_must_be_a_login(self) -> None:
        """An owner that cannot be an account fails before any item."""
        status, log = self.run_main(list="repo#1", validate="issue", owner="a b!")
        self.assertEqual(status, 1)
        self.assertEqual(
            log, "::error::owner must be an organisation or user name, not 'a b!'\n"
        )

    def test_owner_is_required_where_references_need_one(self) -> None:
        """With no owner input and no workflow owner, short forms cannot resolve."""
        self.runner["GITHUB_REPOSITORY_OWNER"] = ""
        status, log = self.run_main(list="repo#1", validate="issue")
        self.assertEqual(status, 1)
        self.assertEqual(
            log, "::error::owner is blank, and GITHUB_REPOSITORY_OWNER is not set\n"
        )

    def test_globs_pass_without_validation(self) -> None:
        """The default mode accepts patterns and compares case exactly."""
        status, _ = self.run_main(list="*-workflows, *-Workflows")
        self.assertEqual(status, 0)
        self.assertEqual(
            read_outputs(self.path)["json"], '["*-workflows","*-Workflows"]'
        )

    def test_blank_list(self) -> None:
        """A blank list succeeds with no items."""
        status, _ = self.run_main(list=" , ", validate="repository")
        self.assertEqual(status, 0)
        self.assertEqual(read_outputs(self.path)["count"], "0")

    def test_repositories_need_no_owner(self) -> None:
        """Without any owner, names publish as before, with none in details."""
        self.runner["GITHUB_REPOSITORY_OWNER"] = ""
        status, _ = self.run_main(list="repo-a", validate="repository")
        self.assertEqual(status, 0)
        self.assertEqual(
            json.loads(read_outputs(self.path)["details"]),
            [{"item": "repo-a", "repo": "repo-a"}],
        )

    def test_repeated_tokens_drop_before_validation(self) -> None:
        """A token repeating an earlier one, ignoring case, is never checked."""
        status, _ = self.run_main(list="k \u212a", validate="repository")
        self.assertEqual(status, 0)
        self.assertEqual(read_outputs(self.path)["json"], '["k"]')

    def test_every_invalid_item_is_reported_once(self) -> None:
        """All failures are named before the step fails; nothing is written."""
        status, log = self.run_main(
            list="good, org/repo bad! org/repo 50%", validate="repository"
        )
        self.assertEqual(status, 1)
        self.assertEqual(
            log.splitlines(),
            [
                "::error::Invalid item 'org/repo': give the repository name alone, without the owner",
                "::error::Invalid item 'bad!': not a valid repository name",
                "::error::Invalid item '50%25': not a valid repository name",
            ],
        )
        self.assertEqual(self.path.read_text(encoding="utf-8"), "")

    def test_bad_inputs_fail_with_an_annotation(self) -> None:
        """An unknown mode or setting fails before any splitting."""
        for inputs in ({"validate": "repo"}, {"ignore_case": "maybe"}):
            with self.subTest(inputs=inputs):
                status, log = self.run_main(list="a", **inputs)
                self.assertEqual(status, 1)
                self.assertTrue(log.startswith("::error::"))
        self.assertEqual(self.path.read_text(encoding="utf-8"), "")

    def test_missing_output_file_fails(self) -> None:
        """Without GITHUB_OUTPUT there is nowhere to publish."""
        log = io.StringIO()
        with redirect_stdout(log):
            status = action.main({"SPLIT_LIST": "a"})
        self.assertEqual(status, 1)
        self.assertEqual(log.getvalue(), "::error::GITHUB_OUTPUT is not set\n")


if __name__ == "__main__":
    unittest.main()
