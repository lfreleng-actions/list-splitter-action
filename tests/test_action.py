# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Unit tests for list_splitter.outputs and list_splitter.action."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from list_splitter import action, outputs  # noqa: E402


def read_outputs(path: Path) -> dict[str, str]:
    """Parse a heredoc-form output file the way the runner does."""
    found: dict[str, str] = {}
    lines = path.read_text(encoding="utf-8").split("\n")
    index = 0
    while index < len(lines) and lines[index]:
        name, _, delimiter = lines[index].partition("<<")
        end = lines.index(delimiter, index + 1)
        found[name] = "\n".join(lines[index + 1 : end])
        index = end + 1
    return found


class OutputFileTestCase(unittest.TestCase):
    """Provides a scratch output file for each test."""

    def setUp(self) -> None:
        """Create an empty output file that is removed afterwards."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.path = Path(holder.name, "output")
        self.path.touch()


class OutputsTest(OutputFileTestCase):
    """Each output renders the same items, and the file cannot be forged."""

    def test_formats(self) -> None:
        """json, csv, lines and count describe the same list."""
        self.assertEqual(
            outputs.build_outputs(["a", "b"]),
            {"json": '["a","b"]', "csv": "a,b", "lines": "a\nb", "count": "2"},
        )

    def test_empty_list(self) -> None:
        """No items gives an empty array and empty text outputs."""
        outputs.write_outputs(str(self.path), outputs.build_outputs([]))
        self.assertEqual(
            read_outputs(self.path),
            {"json": "[]", "csv": "", "lines": "", "count": "0"},
        )

    def test_values_round_trip(self) -> None:
        """Multi-line and non-ASCII values read back unchanged."""
        rendered = outputs.build_outputs(["ä*", "b"])
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


class MainTest(OutputFileTestCase):
    """End to end: environment in, output file and log out."""

    def run_main(self, **inputs: str) -> tuple[int, str]:
        """Run main with the given inputs, returning its status and log."""
        environ = {"GITHUB_OUTPUT": str(self.path)}
        environ.update(
            {f"SPLIT_{name.upper()}": value for name, value in inputs.items()}
        )
        log = io.StringIO()
        with redirect_stdout(log):
            status = action.main(environ)
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
            status = action.main({"SPLIT_LIST": "a"})
        self.assertEqual(status, 1)
        self.assertEqual(log.getvalue(), "::error::GITHUB_OUTPUT is not set\n")


if __name__ == "__main__":
    unittest.main()
