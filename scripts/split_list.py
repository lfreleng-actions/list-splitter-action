# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Split a delimited list into items, then deduplicate and validate them.

action.yaml runs this with the runner's python3. The inputs arrive in
the environment as SPLIT_LIST, SPLIT_VALIDATE and SPLIT_IGNORE_CASE;
the json, csv, lines and count outputs go to $GITHUB_OUTPUT. When any
item fails validation, every failure is reported before the step
fails, so a list with several mistakes needs one corrected re-run.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
from collections.abc import Callable, Mapping

SEPARATORS = re.compile(r"[,\s]+")
# GitHub's rule for a repository name: ASCII letters, digits, '.', '-'
# and '_', at most 100 characters.
REPOSITORY_NAME = re.compile(r"[A-Za-z0-9._-]{1,100}")


class InputError(Exception):
    """An action input the splitter cannot act on."""


def split(text: str) -> list[str]:
    """Split on commas and any whitespace, dropping empty items."""
    return [item for item in SEPARATORS.split(text) if item]


def check_none(_item: str) -> str | None:
    """Accept every item: globs, paths and free-form tokens alike."""
    return None


def check_repository(item: str) -> str | None:
    """Explain why an item is not a bare repository name, or return None."""
    if "/" in item:
        return "give the repository name alone, without the owner"
    # '.' and '..' match the character class but resolve as path
    # segments once placed in an API URL.
    if item in (".", "..") or not REPOSITORY_NAME.fullmatch(item):
        return "not a valid repository name"
    return None


VALIDATORS: dict[str, Callable[[str], str | None]] = {
    "none": check_none,
    "repository": check_repository,
}
# Modes whose items GitHub itself compares without regard to case.
CASE_INSENSITIVE_MODES = frozenset({"repository"})


def resolve_mode(value: str) -> str:
    """Normalise the validate input; blank means none."""
    mode = value.strip().lower() or "none"
    if mode not in VALIDATORS:
        choices = ", ".join(sorted(VALIDATORS))
        raise InputError(f"validate must be one of {choices}, not {value!r}")
    return mode


def resolve_ignore_case(value: str, mode: str) -> bool:
    """Normalise the ignore-case input; auto follows the validate mode."""
    setting = value.strip().lower() or "auto"
    if setting == "auto":
        return mode in CASE_INSENSITIVE_MODES
    if setting in ("true", "false"):
        return setting == "true"
    raise InputError(f"ignore-case must be auto, true or false, not {value!r}")


def dedupe(items: list[str], ignore_case: bool) -> list[str]:
    """Keep the first occurrence of each item, in the order given."""
    seen: set[str] = set()
    kept: list[str] = []
    for item in items:
        key = item.casefold() if ignore_case else item
        if key not in seen:
            seen.add(key)
            kept.append(item)
    return kept


def build_outputs(items: list[str]) -> dict[str, str]:
    """Render the items in each output format the action publishes."""
    return {
        "json": json.dumps(items, ensure_ascii=False, separators=(",", ":")),
        "csv": ",".join(items),
        "lines": "\n".join(items),
        "count": str(len(items)),
    }


def write_outputs(path: str, outputs: Mapping[str, str]) -> None:
    """Append outputs in the heredoc form, under a delimiter absent from each value.

    The heredoc form keeps a value from injecting further keys into
    the output file, whatever it holds.
    """
    with open(path, "a", encoding="utf-8") as sink:
        for name, value in outputs.items():
            delimiter = f"ghadelim_{secrets.token_hex(16)}"
            while delimiter in value:
                delimiter = f"ghadelim_{secrets.token_hex(16)}"
            sink.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")


def escape_command(text: str) -> str:
    """Escape text for the message of a workflow command."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main(environ: Mapping[str, str]) -> int:
    """Split, deduplicate and validate the list, then publish the outputs."""
    output_path = environ.get("GITHUB_OUTPUT", "")
    try:
        if not output_path:
            raise InputError("GITHUB_OUTPUT is not set")
        mode = resolve_mode(environ.get("SPLIT_VALIDATE", ""))
        ignore_case = resolve_ignore_case(environ.get("SPLIT_IGNORE_CASE", ""), mode)
    except InputError as exc:
        print(f"::error::{escape_command(str(exc))}")
        return 1

    items = dedupe(split(environ.get("SPLIT_LIST", "")), ignore_case)
    check = VALIDATORS[mode]
    failures = [(item, reason) for item in items if (reason := check(item))]
    for item, reason in failures:
        print(f"::error::Invalid item '{escape_command(item)}': {reason}")
    if failures:
        return 1

    outputs = build_outputs(items)
    write_outputs(output_path, outputs)
    # Prefixed so that no item can open a line, where the runner
    # would read it as a workflow command.
    print(f"Items ({outputs['count']}): {outputs['json']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(os.environ))
