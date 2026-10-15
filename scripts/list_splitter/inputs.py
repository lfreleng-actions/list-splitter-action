# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Read and check the action inputs, which arrive as SPLIT_* variables."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from . import categories
from .categories.accounts import LOGIN
from .categories.base import Category, Context, Verifiable

# The runner sets GITHUB_SERVER_URL and GITHUB_GRAPHQL_URL, which name
# the right hosts on GitHub Enterprise; these serve runs outside one.
DEFAULT_SERVER_URL = "https://github.com"
DEFAULT_GRAPHQL_URL = "https://api.github.com/graphql"
# Every kind of GitHub token is visible ASCII; anything else cannot
# travel in an HTTP header, and would fail in a way that shows it.
TOKEN = re.compile(r"[\x21-\x7e]+")


class InputError(Exception):
    """An action input the splitter cannot act on."""


@dataclass(frozen=True)
class Verification:
    """How to confirm the items on GitHub, when the verify input asks to."""

    category: Verifiable
    endpoint: str
    token: str = field(repr=False)


@dataclass(frozen=True)
class Settings:
    """The inputs, checked and normalised."""

    category: Category
    ignore_case: bool
    context: Context
    verification: Verification | None = None


def resolve_category(value: str) -> Category:
    """Normalise the validate input; blank means none."""
    category = categories.REGISTRY.get(value.strip().lower() or "none")
    if category is None:
        choices = ", ".join(categories.canonical_names())
        raise InputError(f"validate must be one of {choices}, not {value!r}")
    return category


def resolve_ignore_case(value: str, category: Category) -> bool:
    """Normalise the ignore-case input; auto follows the category."""
    setting = value.strip().lower() or "auto"
    if setting == "auto":
        return category.ignore_case
    if setting in ("true", "false"):
        return setting == "true"
    raise InputError(f"ignore-case must be auto, true or false, not {value!r}")


def resolve_owner(
    value: str, workflow_owner: str, category: Category, verifying: bool = False
) -> str:
    """Normalise the owner input; blank means the workflow's own owner.

    Categories without owners ignore the input, and get blank; so does
    one that can do without an owner when none is known, unless its
    items are to be looked up on GitHub, which takes the owner.
    """
    if not category.has_owner:
        return ""
    owner = value.strip() or workflow_owner.strip()
    if owner and not LOGIN.fullmatch(owner):
        raise InputError(f"owner must be an organisation or user name, not {owner!r}")
    if not owner and (category.needs_owner or verifying):
        raise InputError("owner is blank, and GITHUB_REPOSITORY_OWNER is not set")
    return owner


def resolve_verification(
    value: str, category: Category, environ: Mapping[str, str]
) -> Verification | None:
    """Normalise the verify input, with what verifying needs; blank means false."""
    setting = value.strip().lower() or "false"
    if setting not in ("true", "false"):
        raise InputError(f"verify must be true or false, not {value!r}")
    if setting == "false":
        return None
    if not isinstance(category, Verifiable):
        raise InputError(
            f"verify needs a mode naming GitHub objects, not {category.names[0]}"
        )
    token = environ.get("SPLIT_TOKEN", "").strip()
    if not token:
        raise InputError("verify needs a token, and the token input is blank")
    if not TOKEN.fullmatch(token):
        raise InputError("the token input holds characters no GitHub token has")
    endpoint = environ.get("GITHUB_GRAPHQL_URL", "").strip() or DEFAULT_GRAPHQL_URL
    # The token travels with every query, so never over plain HTTP.
    if not endpoint.startswith("https://"):
        raise InputError(f"GITHUB_GRAPHQL_URL must use https, not {endpoint!r}")
    return Verification(category, endpoint, token)


def read_settings(environ: Mapping[str, str]) -> Settings:
    """Check every input before any item is read."""
    category = resolve_category(environ.get("SPLIT_VALIDATE", ""))
    ignore_case = resolve_ignore_case(environ.get("SPLIT_IGNORE_CASE", ""), category)
    verification = resolve_verification(
        environ.get("SPLIT_VERIFY", ""), category, environ
    )
    owner = resolve_owner(
        environ.get("SPLIT_OWNER", ""),
        environ.get("GITHUB_REPOSITORY_OWNER", ""),
        category,
        verifying=verification is not None,
    )
    server_url = environ.get("GITHUB_SERVER_URL", "").strip() or DEFAULT_SERVER_URL
    return Settings(category, ignore_case, Context(owner, server_url), verification)
