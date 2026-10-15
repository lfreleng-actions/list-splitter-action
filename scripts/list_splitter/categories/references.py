# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""The issue and pull-request modes: numbered references.

Both accept the same five spellings, repo#N, owner/repo#N,
repo/KIND/N, owner/repo/KIND/N and the web address, where KIND is the
URL path segment of their kind, and publish each as owner/repo#N.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from .accounts import LOGIN
from .base import Category, Context, InvalidItem, Item
from .repositories import check_repository_name

NUMBER = re.compile(r"[0-9]{1,10}")
# Verification sends a number as a GraphQL Int, and one value outside
# its 32-bit range would fail every lookup in the same query.
MAX_NUMBER = 2**31 - 1
# What a reference may look like once any URL prefix is removed.
REFERENCE = re.compile(
    r"(?:(?P<owner>[^/#]+)/)?(?P<repo>[^/#]+)"
    r"(?:#(?P<short>[^/#]+)|/(?P<kind>[^/#]+)/(?P<number>[^/#]+)/?)"
)
# The URL path segment naming each kind of numbered item.
KINDS = {"issues": "an issue", "pull": "a pull request"}


@dataclass(frozen=True)
class Reference:
    """The parts of a numbered reference, none of them checked yet."""

    owner: str | None
    repo: str
    kind: str | None
    number: str


def split_reference(token: str, server_url: str) -> Reference | None:
    """Take a numbered reference apart, or return None if it is not one."""
    prefix = f"{server_url.rstrip('/')}/"
    head = token[: len(prefix)]
    # ASCII alone, since some letters fold to ASCII ones: 'ſ' to 's'.
    is_url = head.isascii() and head.lower() == prefix.lower()
    if is_url:
        # A browser adds a query, or a fragment for a comment; neither
        # changes which item the address names.
        token = re.split(r"[?#]", token[len(prefix) :], maxsplit=1)[0]
    found = REFERENCE.fullmatch(token)
    if found is None:
        return None
    kind = found["kind"]
    # A web address always carries the owner and the kind.
    if is_url and (found["owner"] is None or kind is None):
        return None
    number = found["short"] if kind is None else found["number"]
    return Reference(found["owner"], found["repo"], kind, number)


def parse_number(text: str, noun: str) -> int:
    """Read an issue or pull request number GitHub could hold."""
    if not NUMBER.fullmatch(text) or not 0 < int(text) <= MAX_NUMBER:
        raise InvalidItem(f"not a valid {noun} number")
    return int(text)


class NumberedReference(Category):
    """An issue or pull request in a repository of the owner."""

    ignore_case = True
    has_owner = True
    needs_owner = True
    # The URL path segment of the kind, a key of KINDS.
    kind: ClassVar[str]
    # The kind's name, for messages.
    noun: ClassVar[str]

    def parse(self, token: str, context: Context) -> Item:
        """Accept every spelling of a reference, publishing owner/repo#N."""
        wanted = KINDS[self.kind]
        reference = split_reference(token, context.server_url)
        if reference is None or reference.kind not in (None, *KINDS):
            raise InvalidItem(f"not a valid reference to {wanted}")
        if reference.kind not in (None, self.kind):
            raise InvalidItem(f"names {KINDS[reference.kind]}, not {wanted}")
        if reference.owner is not None:
            if not LOGIN.fullmatch(reference.owner):
                raise InvalidItem("not a valid owner name")
            if reference.owner.casefold() != context.owner.casefold():
                raise InvalidItem(f"belongs to {reference.owner}, not {context.owner}")
        check_repository_name(reference.repo)
        number = parse_number(reference.number, self.noun)
        return Item(
            f"{context.owner}/{reference.repo}#{number}",
            owner=context.owner,
            repo=reference.repo,
            number=number,
        )


class Issue(NumberedReference):
    """An issue: repo#N, owner/repo#N, repo/issues/N or its URL."""

    names = ("issue",)
    kind = "issues"
    noun = "issue"


class PullRequest(NumberedReference):
    """A pull request: repo#N, owner/repo#N, repo/pull/N or its URL."""

    names = ("pull-request",)
    kind = "pull"
    noun = "pull request"
