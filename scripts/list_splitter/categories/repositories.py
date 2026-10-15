# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""The repository mode: bare repository names."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from ..graphql import Argument, Lookup, Step, field_of
from .base import NOT_FOUND, Context, InvalidItem, Item, Verifiable, check_place

# GitHub's rule for a repository name: ASCII letters, digits, '.', '-'
# and '_', at most 100 characters.
REPOSITORY_NAME = re.compile(r"[A-Za-z0-9._-]{1,100}")
# What verification reads of a repository: enough to choose which to
# scan, as the organisation's repository discovery does.
SELECTION = (
    "nameWithOwner url isArchived isFork isTemplate isDisabled isPrivate"
    " visibility defaultBranchRef { name }"
)


def check_repository_name(name: str) -> None:
    """Refuse a name GitHub would not accept for a repository."""
    # '.' and '..' match the character class but resolve as path
    # segments once placed in an API URL.
    if name in (".", "..") or not REPOSITORY_NAME.fullmatch(name):
        raise InvalidItem("not a valid repository name")


def repository_step(owner: str, repo: str, missing: str) -> Step:
    """The repository field: the object itself, or the way to one inside it."""
    arguments = (Argument("owner", "String!", owner), Argument("name", "String!", repo))
    return Step("repository", arguments, missing)


class Repository(Verifiable):
    """A bare repository name, without its owner."""

    names = ("repository",)
    ignore_case = True
    has_owner = True

    def parse(self, token: str, context: Context) -> Item:
        """Accept a name GitHub would accept for a repository."""
        if "/" in token:
            raise InvalidItem("give the repository name alone, without the owner")
        check_repository_name(token)
        return Item(token, owner=context.owner, repo=token)

    def lookup(self, item: Item) -> Lookup:
        """The repository, by owner and name."""
        return Lookup((repository_step(item.owner, item.repo, NOT_FOUND),), SELECTION)

    def check(self, item: Item, node: Mapping[str, Any]) -> dict[str, object]:
        """Confirm the repository has not moved; report it as REST names it."""
        check_place(f"{item.owner}/{item.repo}", field_of(node, "nameWithOwner", str))
        # An empty repository has no default branch yet.
        branch = node.get("defaultBranchRef")
        return {
            "html_url": field_of(node, "url", str),
            "default_branch": (
                field_of(branch, "name", str) if isinstance(branch, dict) else None
            ),
            "archived": field_of(node, "isArchived", bool),
            "fork": field_of(node, "isFork", bool),
            "is_template": field_of(node, "isTemplate", bool),
            "disabled": field_of(node, "isDisabled", bool),
            "private": field_of(node, "isPrivate", bool),
            "visibility": field_of(node, "visibility", str).lower(),
        }
