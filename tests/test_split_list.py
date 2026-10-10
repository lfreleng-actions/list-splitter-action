# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Unit tests for scripts/split_list.py."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import split_list  # noqa: E402


def read_outputs(path: Path) -> dict[str, str]:
    """Parse a heredoc-form output file the way the runner does."""
    outputs: dict[str, str] = {}
    lines = path.read_text(encoding="utf-8").split("\n")
    index = 0
    while index < len(lines) and lines[index]:
        name, _, delimiter = lines[index].partition("<<")
        end = lines.index(delimiter, index + 1)
        outputs[name] = "\n".join(lines[index + 1 : end])
        index = end + 1
    return outputs


class SplitTest(unittest.TestCase):
    """Commas and every kind of whitespace separate items."""

    def test_mixed_separators(self) -> None:
        """Commas, spaces, tabs and newlines all split; runs collapse."""
        self.assertEqual(
            split_list.split("a, b c,,d\te\nf\r\n g ,"),
            ["a", "b", "c", "d", "e", "f", "g"],
        )

    def test_blank_and_separator_only_input_yield_nothing(self) -> None:
        """Input holding no item gives an empty list, never an empty item."""
        for text in ("", "   ", ",", " , ,\n\t"):
            with self.subTest(text=text):
                self.assertEqual(split_list.split(text), [])

    def test_items_keep_their_characters(self) -> None:
        """Splitting alters nothing within an item, globs included."""
        self.assertEqual(
            split_list.split("*-workflows ci-[ab]? owner/repo"),
            ["*-workflows", "ci-[ab]?", "owner/repo"],
        )


class DedupeTest(unittest.TestCase):
    """Repeats collapse to the first occurrence, keeping order."""

    def test_exact_comparison(self) -> None:
        """Without ignore-case, items differing in case are distinct."""
        self.assertEqual(
            split_list.dedupe(["b", "A", "b", "a", "A"], ignore_case=False),
            ["b", "A", "a"],
        )

    def test_case_insensitive_comparison_keeps_first_spelling(self) -> None:
        """With ignore-case, the first spelling given survives."""
        self.assertEqual(
            split_list.dedupe(["Repo", "other", "REPO", "repo"], ignore_case=True),
            ["Repo", "other"],
        )


class CheckRepositoryTest(unittest.TestCase):
    """The repository mode accepts bare names GitHub would accept."""

    def test_accepts_valid_names(self) -> None:
        """Letters, digits, dots, dashes and underscores pass."""
        for name in (".github", "a", "repo_1.x-y", "x" * 100):
            with self.subTest(name=name):
                self.assertIsNone(split_list.check_repository(name))

    def test_refuses_an_owner_prefix_by_name(self) -> None:
        """owner/name gets its own message, the likeliest mistake."""
        reason = split_list.check_repository("lfreleng-actions/repo")
        self.assertEqual(reason, "give the repository name alone, without the owner")

    def test_refuses_invalid_names(self) -> None:
        """Path segments, stray characters and over-long names fail."""
        for name in (".", "..", "repo?", "*-workflows", "re po!", "é", "x" * 101):
            with self.subTest(name=name):
                self.assertEqual(
                    split_list.check_repository(name), "not a valid repository name"
                )


class ResolveInputsTest(unittest.TestCase):
    """validate and ignore-case accept their documented spellings alone."""

    def test_mode_defaults_to_none_and_ignores_case_and_padding(self) -> None:
        """Blank selects none; the value is trimmed and case-folded."""
        self.assertEqual(split_list.resolve_mode(""), "none")
        self.assertEqual(split_list.resolve_mode(" Repository "), "repository")

    def test_unknown_mode_is_refused(self) -> None:
        """A typo fails rather than silently skipping validation."""
        with self.assertRaisesRegex(split_list.InputError, "none, repository"):
            split_list.resolve_mode("repo")

    def test_auto_follows_the_mode(self) -> None:
        """auto, or blank, ignores case for repositories alone."""
        for value in ("", "auto", " AUTO "):
            with self.subTest(value=value):
                self.assertTrue(split_list.resolve_ignore_case(value, "repository"))
                self.assertFalse(split_list.resolve_ignore_case(value, "none"))

    def test_explicit_setting_overrides_the_mode(self) -> None:
        """true and false apply whatever the mode."""
        self.assertTrue(split_list.resolve_ignore_case("true", "none"))
        self.assertFalse(split_list.resolve_ignore_case("False", "repository"))

    def test_unknown_ignore_case_is_refused(self) -> None:
        """Only auto, true and false are accepted."""
        with self.assertRaises(split_list.InputError):
            split_list.resolve_ignore_case("yes", "none")


class OutputsTest(unittest.TestCase):
    """Each output renders the same items, and the file cannot be forged."""

    def setUp(self) -> None:
        """Provide a scratch output file."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.path = Path(holder.name, "output")
        self.path.touch()

    def test_formats(self) -> None:
        """json, csv, lines and count describe the same list."""
        self.assertEqual(
            split_list.build_outputs(["a", "b"]),
            {"json": '["a","b"]', "csv": "a,b", "lines": "a\nb", "count": "2"},
        )

    def test_empty_list(self) -> None:
        """No items gives an empty array and empty text outputs."""
        split_list.write_outputs(str(self.path), split_list.build_outputs([]))
        self.assertEqual(
            read_outputs(self.path),
            {"json": "[]", "csv": "", "lines": "", "count": "0"},
        )

    def test_values_round_trip(self) -> None:
        """Multi-line and non-ASCII values read back unchanged."""
        outputs = split_list.build_outputs(["ä*", "b"])
        split_list.write_outputs(str(self.path), outputs)
        self.assertEqual(read_outputs(self.path), outputs)
        self.assertEqual(json.loads(outputs["json"]), ["ä*", "b"])

    def test_value_cannot_inject_a_key(self) -> None:
        """A value shaped like a key line stays inside its own value."""
        hostile = "x\ncount=999\nghadelim_\ninjected<<EOF"
        split_list.write_outputs(str(self.path), {"lines": hostile})
        self.assertEqual(read_outputs(self.path), {"lines": hostile})

    def test_escape_command(self) -> None:
        """Percent signs and line breaks are encoded for the runner."""
        self.assertEqual(split_list.escape_command("50%\r\n::x"), "50%25%0D%0A::x")


class MainTest(unittest.TestCase):
    """End to end: environment in, output file and log out."""

    def setUp(self) -> None:
        """Provide a scratch output file."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.path = Path(holder.name, "output")
        self.path.touch()

    def run_main(self, **inputs: str) -> tuple[int, str]:
        """Run main with the given inputs, returning its status and log."""
        environ = {"GITHUB_OUTPUT": str(self.path)}
        environ.update(
            {f"SPLIT_{name.upper()}": value for name, value in inputs.items()}
        )
        log = io.StringIO()
        with redirect_stdout(log):
            status = split_list.main(environ)
        return status, log.getvalue()

    def test_repository_list(self) -> None:
        """Names split, collapse ignoring case, and keep their order."""
        status, log = self.run_main(
            list="repo-b, Repo-A repo-a\nrepo-b", validate="repository"
        )
        self.assertEqual(status, 0)
        self.assertEqual(
            read_outputs(self.path),
            {
                "json": '["repo-b","Repo-A"]',
                "csv": "repo-b,Repo-A",
                "lines": "repo-b\nRepo-A",
                "count": "2",
            },
        )
        self.assertEqual(log, 'Items (2): ["repo-b","Repo-A"]\n')

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
            status = split_list.main({"SPLIT_LIST": "a"})
        self.assertEqual(status, 1)
        self.assertEqual(log.getvalue(), "::error::GITHUB_OUTPUT is not set\n")


if __name__ == "__main__":
    unittest.main()
