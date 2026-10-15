# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""What every validate mode provides, and what it hands back."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from ..graphql import Lookup

# Why verification fails when GitHub returns nothing: a private object
# the token cannot see looks exactly like one that does not exist.
NOT_FOUND = "not found on GitHub, or not visible to the token"


class InvalidItem(Exception):
    """Why a token is not an item of the selected category."""


def check_place(expected: str, actual: str) -> None:
    """Refuse an item GitHub now keeps elsewhere.

    GitHub follows a renamed or transferred repository, and a moved
    issue, to where it lives now. The list still names the old place,
    which may belong to another owner.
    """
    if actual.casefold() != expected.casefold():
        raise InvalidItem(f"has moved to {actual}")


@dataclass(frozen=True)
class Context:
    """What a category needs, beyond the token, to read it."""

    # The owner that references belong to; blank where the category
    # takes none, or can do without one and none is known.
    owner: str
    # The web address that URL references start with.
    server_url: str


@dataclass(frozen=True)
class Item:
    """One accepted token, in the forms the outputs publish."""

    # The item as the json, csv and lines outputs publish it; tokens
    # naming the same item share it.
    text: str
    # Where the item sits on GitHub, as far as its category places it:
    # the repository's owner and name, the issue or pull request
    # number, the account name. Blank or zero where they do not apply.
    owner: str = ""
    repo: str = ""
    number: int = 0
    login: str = ""
    # What GitHub reported about the item, once verified.
    facts: dict[str, object] = field(default_factory=dict, hash=False)

    @property
    def details(self) -> dict[str, object]:
        """The item's entry in the details output."""
        located: dict[str, object] = {
            "owner": self.owner,
            "repo": self.repo,
            "number": self.number,
            "login": self.login,
        }
        placed = {key: value for key, value in located.items() if value}
        return {"item": self.text, **placed, **self.facts}


class Category(ABC):
    """One validate mode: what an item looks like, and how GitHub compares it."""

    # Spellings the validate input accepts; the first is the canonical one.
    names: ClassVar[tuple[str, ...]]
    # Whether GitHub compares items without regard to case; the
    # ignore-case input follows this when set to auto.
    ignore_case: ClassVar[bool]
    # Whether items belong to an owner, which details then names.
    has_owner: ClassVar[bool] = False
    # Whether reading an item takes the owner, so a blank one fails.
    needs_owner: ClassVar[bool] = False

    @abstractmethod
    def parse(self, token: str, context: Context) -> Item:
        """Return the item a token names, or raise InvalidItem saying why not."""


class Verifiable(Category):
    """A category whose items GitHub can confirm, for the verify input."""

    @abstractmethod
    def lookup(self, item: Item) -> Lookup:
        """Where on GitHub the item should be, and what to read there."""

    @abstractmethod
    def check(self, item: Item, node: Mapping[str, Any]) -> dict[str, object]:
        """Confirm GitHub's object is the item, returning facts for details.

        Raise InvalidItem when GitHub holds something else there, such
        as a pull request where the list named an issue.
        """
