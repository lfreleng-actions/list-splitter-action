# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""What every validate mode provides, and what it hands back."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar


class InvalidItem(Exception):
    """Why a token is not an item of the selected category."""


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

    @property
    def details(self) -> dict[str, object]:
        """The item's entry in the details output."""
        located: dict[str, object] = {
            "owner": self.owner,
            "repo": self.repo,
            "number": self.number,
            "login": self.login,
        }
        return {"item": self.text, **{k: v for k, v in located.items() if v}}


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
