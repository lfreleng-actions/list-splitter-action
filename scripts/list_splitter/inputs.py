# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Read and check the action inputs, which arrive as SPLIT_* variables."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from . import categories
from .categories.accounts import LOGIN
from .categories.base import Category, Context

# The runner sets GITHUB_SERVER_URL; this serves runs outside one.
DEFAULT_SERVER_URL = "https://github.com"


class InputError(Exception):
    """An action input the splitter cannot act on."""


@dataclass(frozen=True)
class Settings:
    """The inputs, checked and normalised."""

    category: Category
    ignore_case: bool
    context: Context


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


def resolve_owner(value: str, workflow_owner: str, category: Category) -> str:
    """Normalise the owner input; blank means the workflow's own owner.

    Categories without owners ignore the input, and get blank; so does
    one that can do without an owner when none is known.
    """
    if not category.has_owner:
        return ""
    owner = value.strip() or workflow_owner.strip()
    if owner and not LOGIN.fullmatch(owner):
        raise InputError(f"owner must be an organisation or user name, not {owner!r}")
    if not owner and category.needs_owner:
        raise InputError("owner is blank, and GITHUB_REPOSITORY_OWNER is not set")
    return owner


def read_settings(environ: Mapping[str, str]) -> Settings:
    """Check every input before any item is read."""
    category = resolve_category(environ.get("SPLIT_VALIDATE", ""))
    ignore_case = resolve_ignore_case(environ.get("SPLIT_IGNORE_CASE", ""), category)
    owner = resolve_owner(
        environ.get("SPLIT_OWNER", ""),
        environ.get("GITHUB_REPOSITORY_OWNER", ""),
        category,
    )
    server_url = environ.get("GITHUB_SERVER_URL", "").strip() or DEFAULT_SERVER_URL
    return Settings(category, ignore_case, Context(owner, server_url))
