# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""The none mode: tokens taken as they are."""

from __future__ import annotations

from .base import Category, Context, Item


class AnyToken(Category):
    """Accept every token: globs, paths and free-form tokens alike."""

    names = ("none",)
    ignore_case = False

    def parse(self, token: str, context: Context) -> Item:
        """Return the token unchanged."""
        return Item(token)
