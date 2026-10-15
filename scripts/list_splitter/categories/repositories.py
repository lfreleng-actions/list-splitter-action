# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""The repository mode: bare repository names."""

from __future__ import annotations

import re

from .base import Category, Context, InvalidItem, Item

# GitHub's rule for a repository name: ASCII letters, digits, '.', '-'
# and '_', at most 100 characters.
REPOSITORY_NAME = re.compile(r"[A-Za-z0-9._-]{1,100}")


def check_repository_name(name: str) -> None:
    """Refuse a name GitHub would not accept for a repository."""
    # '.' and '..' match the character class but resolve as path
    # segments once placed in an API URL.
    if name in (".", "..") or not REPOSITORY_NAME.fullmatch(name):
        raise InvalidItem("not a valid repository name")


class Repository(Category):
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
