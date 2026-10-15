# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Run the action's main as the runner would, for the end-to-end tests."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from list_splitter import action  # noqa: E402
from list_splitter.graphql import Transport  # noqa: E402

# The runner sets GITHUB_REPOSITORY_OWNER in every job.
WORKFLOW_OWNER = "lfreleng-actions"


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


class ActionTestCase(OutputFileTestCase):
    """Runs main with inputs, as the runner would, and reads what it left."""

    # Stands in for GitHub when a test turns verify on.
    transport: Transport | None = None

    def setUp(self) -> None:
        """Provide the output file, and the variables the runner sets."""
        super().setUp()
        self.runner = {
            "GITHUB_OUTPUT": str(self.path),
            "GITHUB_REPOSITORY_OWNER": WORKFLOW_OWNER,
        }

    def run_main(self, **inputs: str) -> tuple[int, str]:
        """Run main with the given inputs, returning its status and log."""
        environ = dict(self.runner)
        environ.update(
            {f"SPLIT_{name.upper()}": value for name, value in inputs.items()}
        )
        log = io.StringIO()
        with redirect_stdout(log):
            status = action.main(environ, self.transport)
        return status, log.getvalue()

    def assertRefusals(self, log: str, refusals: list[tuple[str, str]]) -> None:
        """The log names exactly these tokens and reasons, in this order."""
        self.assertEqual(
            log.splitlines(),
            [f"::error::Invalid item '{token}': {why}" for token, why in refusals],
        )
        self.assertEqual(self.path.read_text(encoding="utf-8"), "")
