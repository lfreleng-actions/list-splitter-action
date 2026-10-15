# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""The validate modes, each a category of item held in one registry.

A category says what a valid item looks like and how GitHub compares
items of its kind; base.Category sets out what each provides. To add
a validate mode, write a Category in a module of this package and add
an instance to CATEGORIES; the inputs and the error report read the
registry, so nothing else needs to change.
"""

from __future__ import annotations

from .base import Category
from .repositories import Repository
from .unchecked import AnyToken

CATEGORIES: tuple[Category, ...] = (AnyToken(), Repository())
REGISTRY: dict[str, Category] = {
    name: category for category in CATEGORIES for name in category.names
}


def canonical_names() -> list[str]:
    """The canonical name of every category, sorted, for error messages."""
    return sorted(category.names[0] for category in CATEGORIES)
