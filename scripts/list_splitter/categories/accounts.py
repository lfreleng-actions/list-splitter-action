# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""The organisation and user modes: GitHub account names."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, ClassVar

from ..graphql import Argument, Lookup, Step, field_of
from .base import NOT_FOUND, Context, InvalidItem, Item, Verifiable

# An organisation or user name, by structure: letters, digits, hyphens
# and underscores, at most 39 characters, not starting with a hyphen.
# Underscores are for enterprise managed users, whose names end in an
# underscore and short code.
#
# Hyphen placement is not policed. GitHub's signup form refuses
# consecutive and trailing hyphens, but real accounts break both
# rules: a--b--t is an organisation, and johan-- a user with two
# thousand repositories. As in dependamerge's owner check, this stops
# rubbish without reimplementing GitHub's account policy: too strict
# refuses an account that exists, too lenient costs a not-found error,
# which verify reports. A leading hyphen is refused, as no such account
# is known and the likelier cause is a mistyped option.
LOGIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,38}")
# The account types GitHub's repositoryOwner field returns.
ACCOUNT_TYPES = {"Organization": "an organisation", "User": "a user"}


class Account(Verifiable):
    """An organisation or user, named by its login."""

    ignore_case = True
    # The kind of account, for messages.
    noun: ClassVar[str]
    # The GraphQL type of the kind, a key of ACCOUNT_TYPES.
    typename: ClassVar[str]

    def parse(self, token: str, context: Context) -> Item:
        """Accept a name GitHub would accept for an account."""
        if not LOGIN.fullmatch(token):
            raise InvalidItem(f"not a valid {self.noun} name")
        return Item(token, login=token)

    def lookup(self, item: Item) -> Lookup:
        """The account by login, of either type, to tell the two apart."""
        login = (Argument("login", "String!", item.login),)
        return Lookup((Step("repositoryOwner", login, NOT_FOUND),), "__typename url")

    def check(self, item: Item, node: Mapping[str, Any]) -> dict[str, object]:
        """Confirm the account is of the kind the mode names."""
        typename = field_of(node, "__typename", str)
        if typename != self.typename:
            found = ACCOUNT_TYPES.get(typename, typename)
            raise InvalidItem(f"is {found}, not {ACCOUNT_TYPES[self.typename]}")
        return {"html_url": field_of(node, "url", str)}


class Organisation(Account):
    """An organisation, named by its login."""

    names = ("organisation", "organization")
    noun = "organisation"
    typename = "Organization"


class User(Account):
    """A personal account, named by its login."""

    names = ("user",)
    noun = "user"
    typename = "User"
