# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""The action's flow: check the inputs, split the list, publish the items.

When any item fails validation, every failure is reported before the
step fails, so a list with several mistakes needs one corrected
re-run, and nothing is published.
"""

from __future__ import annotations

from collections.abc import Mapping

from . import tokens
from .categories.base import InvalidItem
from .inputs import InputError, Settings, read_settings
from .outputs import build_outputs, report_error, write_outputs


def collect(text: str, settings: Settings) -> tuple[list[str], list[tuple[str, str]]]:
    """Split and deduplicate the list, then parse each token.

    Returns the items, and each refused token with the reason why.
    """
    items: list[str] = []
    failures: list[tuple[str, str]] = []
    for token in tokens.dedupe(tokens.split(text), settings.ignore_case):
        try:
            items.append(settings.category.parse(token))
        except InvalidItem as exc:
            failures.append((token, str(exc)))
    return items, failures


def main(environ: Mapping[str, str]) -> int:
    """Split, deduplicate and validate the list, then publish the outputs."""
    output_path = environ.get("GITHUB_OUTPUT", "")
    try:
        if not output_path:
            raise InputError("GITHUB_OUTPUT is not set")
        settings = read_settings(environ)
    except InputError as exc:
        report_error(str(exc))
        return 1

    items, failures = collect(environ.get("SPLIT_LIST", ""), settings)
    for token, reason in failures:
        report_error(f"Invalid item '{token}': {reason}")
    if failures:
        return 1

    outputs = build_outputs(items)
    write_outputs(output_path, outputs)
    # Prefixed so that no item can open a line, where the runner
    # would read it as a workflow command.
    print(f"Items ({outputs['count']}): {outputs['json']}")
    return 0
