# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""The action's flow: check the inputs, split the list, publish the items.

When any item fails validation, every failure is reported before the
step fails, so a list with several mistakes needs one corrected
re-run, and nothing is published. Verification checks the items that
passed every offline check, even when others failed, for the same
reason.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import NamedTuple

from . import graphql, tokens
from .categories.base import InvalidItem, Item, Verifiable
from .graphql import Absent, GitHubError, HttpTransport, Transport
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


def confirm(
    items: Sequence[Item], category: Verifiable, transport: Transport
) -> tuple[list[Item], list[Failure]]:
    """Look every item up on GitHub, adding what GitHub reports to each.

    Returns the confirmed items, and each item GitHub does not hold as
    its category describes, with the reason why.
    """
    results = graphql.look_up([category.lookup(item) for item in items], transport)
    confirmed: list[Item] = []
    failures: list[Failure] = []
    for item, result in zip(items, results, strict=True):
        try:
            if isinstance(result, Absent):
                raise InvalidItem(result.reason)
            facts = category.check(item, result.node)
        except InvalidItem as exc:
            failures.append(Failure(item.text, str(exc)))
            continue
        confirmed.append(replace(item, facts=facts))
    return confirmed, failures


def main(environ: Mapping[str, str], transport: Transport | None = None) -> int:
    """Split, deduplicate and validate the list, then publish the outputs.

    ``transport`` stands in for GitHub's GraphQL endpoint, for tests.
    """
    output_path = environ.get("GITHUB_OUTPUT", "")
    try:
        if not output_path:
            raise InputError("GITHUB_OUTPUT is not set")
        settings = read_settings(environ)
    except InputError as exc:
        report_error(str(exc))
        return 1

    items, failures = collect(environ.get("SPLIT_LIST", ""), settings)
    verification = settings.verification
    outage = ""
    if verification and items:
        sender = transport or HttpTransport(verification.endpoint, verification.token)
        try:
            items, refused = confirm(items, verification.category, sender)
            failures.extend(refused)
        except GitHubError as exc:
            outage = f"Could not verify the items on GitHub: {exc}"
    for failure in failures:
        report_error(f"Invalid item '{failure.token}': {failure.reason}")
    if outage:
        report_error(outage)
    if failures or outage:
        return 1

    outputs = build_outputs(items)
    write_outputs(output_path, outputs)
    if verification and items:
        queries = len(graphql.batch_sizes(len(items)))
        noun = "query" if queries == 1 else "queries"
        print(f"Verified on GitHub with {queries} GraphQL {noun}")
    # Prefixed so that no item can open a line, where the runner
    # would read it as a workflow command.
    print(f"Items ({outputs['count']}): {outputs['json']}")
    return 0
