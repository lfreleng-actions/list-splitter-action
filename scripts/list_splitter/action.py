# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""The action's flow: check the inputs, split the list, publish the items.

When any item fails validation, every failure is reported before the
step fails, so a list with several mistakes needs one corrected
re-run, and nothing is published.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple

from . import tokens
from .categories.base import InvalidItem, Item
from .inputs import InputError, Settings, read_settings
from .outputs import build_outputs, report_error, write_outputs


class Failure(NamedTuple):
    """A token that failed validation, and the reason why."""

    token: str
    reason: str


def collect(text: str, settings: Settings) -> tuple[list[Item], list[Failure]]:
    """Split and deduplicate the list, parse each token, then drop repeats.

    Tokens naming one item, such as repo#1 and its URL, are repeats
    too, so items compare once more by the form they publish.
    """
    items: list[Item] = []
    failures: list[Failure] = []
    for token in tokens.dedupe(tokens.split(text), str, settings.ignore_case):
        try:
            items.append(settings.category.parse(token, settings.context))
        except InvalidItem as exc:
            failures.append(Failure(token, str(exc)))
    return tokens.dedupe(items, lambda item: item.text, settings.ignore_case), failures


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
    for failure in failures:
        report_error(f"Invalid item '{failure.token}': {failure.reason}")
    if failures:
        return 1

    outputs = build_outputs(items)
    write_outputs(output_path, outputs)
    # Prefixed so that no item can open a line, where the runner
    # would read it as a workflow command.
    print(f"Items ({outputs['count']}): {outputs['json']}")
    return 0
