# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""The organisation and user modes: GitHub account names."""

from __future__ import annotations

import re
from typing import ClassVar

from .base import Category, Context, InvalidItem, Item

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


class Account(Category):
    """An organisation or user, named by its login."""

    ignore_case = True
    # The kind of account, for messages.
    noun: ClassVar[str]

    def parse(self, token: str, context: Context) -> Item:
        """Accept a name GitHub would accept for an account."""
        if not LOGIN.fullmatch(token):
            raise InvalidItem(f"not a valid {self.noun} name")
        return Item(token, login=token)


class Organisation(Account):
    """An organisation, named by its login."""

    names = ("organisation", "organization")
    noun = "organisation"


class User(Account):
    """A personal account, named by its login."""

    names = ("user",)
    noun = "user"
